"""CUPS integration for GPP SharedPrinter preferences."""

from __future__ import annotations

import logging
import pwd
import subprocess
from typing import Optional

from endeavour_gpo.notify import notify_user
from endeavour_gpo.printers.parser import ACTION_CREATE, ACTION_REPLACE, SharedPrinterMap

log = logging.getLogger(__name__)


class PrinterApplyError(RuntimeError):
    pass


class CupsPrinterApplier:
    """Apply SharedPrinter maps via lpadmin / lpoptions / lpstat."""

    def __init__(self, username: str, *, uid: Optional[int] = None):
        self.username = username
        self.user_sam = username.split("\\")[-1]
        if uid is not None:
            self.uid = uid
        else:
            self.uid = pwd.getpwnam(self.user_sam).pw_uid

    def apply(self, printer: SharedPrinterMap) -> str:
        if printer.should_delete:
            self.delete(printer)
            return printer.queue_name()

        queue = printer.queue_name()
        uri = printer.smb_uri()
        if not uri:
            raise PrinterApplyError(f"SharedPrinter {printer.uid} has no UNC path")

        exists = self._queue_exists(queue)
        if printer.action == ACTION_CREATE and exists:
            log.debug("Queue already exists (Create): %s", queue)
        else:
            if printer.action == ACTION_REPLACE and exists:
                self._lpadmin_delete(queue)
                exists = False
            self._ensure_queue(printer, queue, uri, update=exists)

        if printer.default:
            self._maybe_set_default(printer, queue)
        return queue

    def delete(self, printer: SharedPrinterMap) -> None:
        if printer.delete_all:
            for queue in self._endeavour_queues():
                self._lpadmin_delete(queue)
            return
        queue = printer.queue_name()
        if self._queue_exists(queue):
            self._lpadmin_delete(queue)

    def notify_failure(self, printer: SharedPrinterMap, error: str) -> None:
        label = printer.name or printer.path or printer.uid or "?"
        notify_user(
            self.uid,
            self.user_sam,
            "Drucker konnte nicht eingerichtet werden",
            "%s: %s" % (label, error),
        )

    def _ensure_queue(
        self,
        printer: SharedPrinterMap,
        queue: str,
        uri: str,
        *,
        update: bool,
    ) -> None:
        base = [
            "lpadmin",
            "-p",
            queue,
            "-v",
            uri,
            "-o",
            "auth-info-required=negotiate",
            "-E",
        ]
        if printer.location:
            base.extend(["-L", printer.location])
        if printer.comment or printer.name:
            base.extend(["-D", printer.comment or printer.name])

        # smb:// is not IPP Everywhere — try raw first to avoid noisy fallbacks.
        models = ("raw",) if uri.startswith("smb:") else ("everywhere", "raw")
        for model in models:
            cmd = list(base) + ["-m", model]
            log.info(
                "%s CUPS queue %s -> %s (-m %s)",
                "Updating" if update else "Creating",
                queue,
                uri,
                model,
            )
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                return
            err = proc.stderr.strip() or proc.stdout.strip() or "lpadmin failed"
            if model != models[-1]:
                log.warning("lpadmin -m %s failed for %s: %s; trying next", model, queue, err)
                continue
            self.notify_failure(printer, err)
            raise PrinterApplyError(err)

    def _maybe_set_default(self, printer: SharedPrinterMap, queue: str) -> None:
        if printer.skip_local and self._has_non_smb_local_printer():
            log.info("skipLocal: lokaler Nicht-SMB-Drucker vorhanden; Default nicht %s", queue)
            return
        proc = subprocess.run(["lpoptions", "-d", queue], capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "lpoptions failed"
            self.notify_failure(printer, err)
            raise PrinterApplyError(err)

    def _lpadmin_delete(self, queue: str) -> None:
        log.info("Removing CUPS queue %s", queue)
        proc = subprocess.run(["lpadmin", "-x", queue], capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "lpadmin -x failed"
            lower = err.lower()
            if "unknown" in lower or "nicht gefunden" in lower or "not found" in lower:
                return
            raise PrinterApplyError(err)

    def _queue_exists(self, queue: str) -> bool:
        proc = subprocess.run(["lpstat", "-p", queue], capture_output=True, text=True)
        return proc.returncode == 0

    def _has_non_smb_local_printer(self) -> bool:
        proc = subprocess.run(["lpstat", "-v"], capture_output=True, text=True)
        if proc.returncode != 0:
            return False
        for line in proc.stdout.splitlines():
            if ":" not in line:
                continue
            uri = line.split(":", 1)[1].strip().lower()
            if uri and not uri.startswith("smb:"):
                return True
        return False

    def _endeavour_queues(self) -> list[str]:
        proc = subprocess.run(["lpstat", "-a"], capture_output=True, text=True)
        if proc.returncode != 0:
            return []
        queues: list[str] = []
        for line in proc.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].startswith("endeavour-"):
                queues.append(parts[0])
        return queues

    def rsop_line(self, printer: SharedPrinterMap) -> str:
        queue = printer.queue_name()
        if printer.should_delete:
            if printer.delete_all:
                return "lpadmin -x <endeavour-*>"
            return "lpadmin -x %s" % queue
        uri = printer.smb_uri()
        bits = [
        "lpadmin -p %s -v %s -m raw -o auth-info-required=negotiate -E" % (queue, uri)
    ]
        if printer.location:
            bits.append("-L %r" % printer.location)
        if printer.comment or printer.name:
            bits.append("-D %r" % (printer.comment or printer.name))
        if printer.default:
            bits.append("; lpoptions -d %s" % queue)
        return " ".join(bits)
