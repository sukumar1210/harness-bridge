from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
from typing import Any

import httpx
from rich.console import Console

from harness_bridge.core.types import TaskSpec
from harness_bridge.drivers.registry import list_all_harness_info
from harness_bridge.session.manager import SessionManager

logger = logging.getLogger("harness-bridge.worker")
console = Console()
err_console = Console(stderr=True)


class WorkerDaemon:
    """Background worker daemon that polls/listens to Harness Bridge over SSE and executes tasks natively."""

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        token: str | None = None,
        harnesses: list[str] | None = None,
        worker_id: str | None = None,
        session_manager: SessionManager | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.session_manager = session_manager or SessionManager()

        host_name = platform.node() or "worker"
        self.worker_id = worker_id or f"worker-{host_name}-{os.getpid()}"

        if harnesses is not None:
            self.harnesses = harnesses
        else:
            detected = [h.name for h in list_all_harness_info() if h.installed]
            self.harnesses = detected

        self._running = False
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

    def _get_headers(self) -> dict[str, str]:
        headers = {"User-Agent": f"HarnessBridge-Worker/{self.worker_id}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def run(self) -> None:
        """Run the worker loop indefinitely until interrupted."""
        self._running = True
        logger.info(
            "Starting WorkerDaemon '%s' -> %s (harnesses: %s)",
            self.worker_id,
            self.server_url,
            self.harnesses,
        )

        backoff = 1.0
        max_backoff = 30.0

        while self._running:
            try:
                await self._listen_stream()
                backoff = 1.0  # Reset backoff on clean connection
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    "Worker connection to %s failed: %s. Retrying in %.1fs...",
                    self.server_url,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, max_backoff)

    def stop(self) -> None:
        """Stop worker daemon."""
        self._running = False
        for t in list(self._active_tasks.values()):
            if not t.done():
                t.cancel()

    async def _listen_stream(self) -> None:
        """Connect to SSE endpoint and stream events."""
        harness_csv = ",".join(self.harnesses)
        url = (
            f"{self.server_url}/api/v1/workers/events"
            f"?worker_id={self.worker_id}&harnesses={harness_csv}&device={platform.node()}"
        )

        # Use None timeout for infinite SSE streaming
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url, headers=self._get_headers()) as response:
                if response.status_code == 401:
                    raise PermissionError("Authentication failed: invalid HARNESS_BRIDGE_TOKEN")
                if response.status_code != 200:
                    raise RuntimeError(f"Server returned status {response.status_code}")

                logger.info("Connected to Harness Bridge SSE stream at %s", self.server_url)

                event_type = ""
                data_lines: list[str] = []

                async for raw_line in response.aiter_lines():
                    if not self._running:
                        break
                    line = raw_line.strip()
                    if not line:
                        # Dispatch complete event block
                        if event_type and data_lines:
                            data_str = "\n".join(data_lines)
                            await self._dispatch_event(event_type, data_str)
                        event_type = ""
                        data_lines = []
                        continue

                    if line.startswith(":"):
                        # SSE keepalive comment
                        continue
                    elif line.startswith("event:"):
                        event_type = line[len("event:") :].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[len("data:") :].strip())

    async def _dispatch_event(self, event_type: str, data_str: str) -> None:
        """Process received SSE event."""
        if event_type == "ping":
            return

        if event_type == "task_offer":
            try:
                task_data = json.loads(data_str)
                task_id = task_data["task_id"]
                t = asyncio.create_task(self._execute_task(task_data))
                self._active_tasks[task_id] = t
                t.add_done_callback(lambda _: self._active_tasks.pop(task_id, None))
            except Exception as exc:
                logger.error("Failed to parse task_offer event: %s (data: %s)", exc, data_str)

    async def _execute_task(self, task_data: dict[str, Any]) -> None:
        """Acknowledge task, send heartbeats, execute turn locally, and post results."""
        task_id = task_data["task_id"]
        session_id = task_data["session_id"]
        harness = task_data["harness"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Acknowledge task lease
            ack_url = f"{self.server_url}/api/v1/tasks/{task_id}/ack"
            try:
                ack_resp = await client.post(
                    ack_url,
                    json={"worker_id": self.worker_id},
                    headers=self._get_headers(),
                )
                if ack_resp.status_code != 200:
                    logger.warning(
                        "Task '%s' ACK rejected with status %d (already claimed)",
                        task_id,
                        ack_resp.status_code,
                    )
                    return
            except Exception as exc:
                logger.error("Failed to ACK task '%s': %s", task_id, exc)
                return

            logger.info("Claimed task '%s' for session '%s' (%s)", task_id, session_id, harness)

            # 2. Heartbeat loop in background
            heartbeat_active = True

            async def _heartbeat_worker() -> None:
                hb_url = f"{self.server_url}/api/v1/tasks/{task_id}/heartbeat"
                while heartbeat_active:
                    await asyncio.sleep(15.0)
                    if not heartbeat_active:
                        break
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as hb_client:
                            await hb_client.post(
                                hb_url,
                                json={"worker_id": self.worker_id},
                                headers=self._get_headers(),
                            )
                    except Exception as e:
                        logger.warning("Heartbeat failed for task '%s': %s", task_id, e)

            hb_task = asyncio.create_task(_heartbeat_worker())

            # 3. Execute locally
            spec = TaskSpec(
                harness=harness,
                prompt=task_data["prompt"],
                session_id=session_id,
                task_id=task_id,
                workspace_mode=task_data.get("workspace_mode", "inherit"),
                timeout_seconds=task_data.get("timeout_seconds", 300),
                repo_root=task_data.get("repo_root"),
            )

            try:
                result = await self.session_manager.execute_task(spec)
                result.task_id = task_id

                # 4. Post complete
                complete_url = f"{self.server_url}/api/v1/tasks/{task_id}/complete"
                await client.post(
                    complete_url,
                    json={"worker_id": self.worker_id, "result": result.model_dump()},
                    headers=self._get_headers(),
                )
                logger.info("Successfully completed task '%s'", task_id)
            except Exception as exc:
                logger.error("Task '%s' failed during execution: %s", task_id, exc)
                fail_url = f"{self.server_url}/api/v1/tasks/{task_id}/fail"
                try:
                    await client.post(
                        fail_url,
                        json={"worker_id": self.worker_id, "error": str(exc), "exit_code": 1},
                        headers=self._get_headers(),
                    )
                except Exception as post_err:
                    logger.error("Failed to post failure for task '%s': %s", task_id, post_err)
            finally:
                heartbeat_active = False
                hb_task.cancel()
                try:
                    await hb_task
                except asyncio.CancelledError:
                    pass
