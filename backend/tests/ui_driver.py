"""Drive the Android app on an emulator via adb.

Capabilities:
  - find element bounds in the current UI by `text=` (exact) or `contains=` (substring)
  - tap an element by text
  - type text into the currently-focused field
  - screenshot
  - assert that some text appears (or doesn't appear) on the current screen
  - wait_for(text, timeout) — poll until present

Usage (script form):
    python -m tests.ui_driver smoke
    python -m tests.ui_driver run --category single_direct
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


# ---- adb plumbing -----------------------------------------------------------

SDK = os.environ.get("ANDROID_SDK_ROOT", r"C:\Users\019158958\AppData\Local\Android\Sdk")
ADB = os.environ.get("ADB", os.path.join(SDK, "platform-tools", "adb.exe"))
SCREENS_DIR = Path(__file__).resolve().parents[2] / "ui_test_screens"
SCREENS_DIR.mkdir(parents=True, exist_ok=True)


def adb(*args: str, capture: bool = True, timeout: int = 30) -> str:
    cmd = [ADB] + list(args)
    # Force UTF-8 decoding — adb output can include smart quotes and other
    # non-CP1252 bytes (Windows default codec).
    res = subprocess.run(
        cmd, capture_output=capture, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if res.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def adb_shell(*args: str, timeout: int = 30) -> str:
    return adb("shell", *args, timeout=timeout)


def screenshot(name: str) -> Path:
    path = SCREENS_DIR / f"{name}.png"
    res = subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True, timeout=20)
    if res.returncode != 0:
        raise RuntimeError(f"screencap failed: {res.stderr.decode()}")
    path.write_bytes(res.stdout)
    return path


# ---- UI hierarchy parsing ---------------------------------------------------

@dataclass
class UiNode:
    text: str
    desc: str
    cls: str
    bounds: tuple[int, int, int, int]  # x1,y1,x2,y2

    @property
    def cx(self) -> int:
        return (self.bounds[0] + self.bounds[2]) // 2

    @property
    def cy(self) -> int:
        return (self.bounds[1] + self.bounds[3]) // 2


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def dump_ui(retry: int = 3) -> list[UiNode]:
    last_err = None
    for _ in range(retry):
        try:
            adb_shell("uiautomator", "dump", "/sdcard/ui.xml")
            xml = adb_shell("cat", "/sdcard/ui.xml")
            root = ET.fromstring(xml.encode("utf-8", errors="replace"))
            return list(_iter_nodes(root))
        except Exception as exc:
            last_err = exc
            time.sleep(0.5)
    raise RuntimeError(f"uiautomator dump failed: {last_err}")


def _iter_nodes(elem) -> Iterable[UiNode]:
    for n in elem.iter("node"):
        b = n.attrib.get("bounds", "")
        m = _BOUNDS_RE.match(b)
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        yield UiNode(
            text=n.attrib.get("text", "") or "",
            desc=n.attrib.get("content-desc", "") or "",
            cls=n.attrib.get("class", "") or "",
            bounds=(x1, y1, x2, y2),
        )


def find_by_text(nodes: list[UiNode], text: str, *, contains: bool = False) -> UiNode | None:
    for n in nodes:
        haystack = (n.text or "") + " " + (n.desc or "")
        if contains:
            if text.lower() in haystack.lower():
                return n
        else:
            if n.text == text or n.desc == text:
                return n
    return None


def wait_for(text: str, *, contains: bool = True, timeout: float = 30.0) -> UiNode:
    deadline = time.time() + timeout
    last_nodes: list[UiNode] = []
    while time.time() < deadline:
        last_nodes = dump_ui()
        hit = find_by_text(last_nodes, text, contains=contains)
        if hit:
            return hit
        time.sleep(0.6)
    snippet = ", ".join(repr((n.text or n.desc)[:40]) for n in last_nodes if n.text or n.desc)[:400]
    raise TimeoutError(f"wait_for({text!r}) timed out. Visible texts: {snippet}")


def tap(x: int, y: int) -> None:
    adb_shell("input", "tap", str(x), str(y))


def tap_text(text: str, *, contains: bool = True, timeout: float = 10.0) -> None:
    node = wait_for(text, contains=contains, timeout=timeout)
    tap(node.cx, node.cy)


def back() -> None:
    adb_shell("input", "keyevent", "KEYCODE_BACK")


def type_text(s: str) -> None:
    # Strip characters outside ASCII printable range to avoid breaking
    # `adb shell input text` (it crashes on certain unicode).
    s = "".join(c for c in s if 0x20 <= ord(c) < 0x7F)
    escaped = (s
               .replace(" ", "%s")
               .replace("&", r"\&")
               .replace("'", r"\'")
               .replace('"', r'\"')
               .replace("?", r"\?")
               .replace("!", r"\!")
               .replace("(", r"\(")
               .replace(")", r"\)")
               .replace("<", r"\<")
               .replace(">", r"\>"))
    adb_shell("input", "text", escaped)


def clear_field(repeats: int = 60) -> None:
    """Select all and delete in the currently-focused field.

    Batches the keyevents into a single shell command to avoid one adb
    roundtrip per keystroke.
    """
    adb_shell("input", "keyevent", "KEYCODE_MOVE_END", timeout=15)
    # One shell exec emits N DELs sequentially — much faster than N exec()s.
    seq = ";".join(["input keyevent KEYCODE_DEL"] * repeats)
    adb_shell("sh", "-c", seq, timeout=60)


# ---- App-specific helpers ---------------------------------------------------

PKG = "com.example.final_project"


def stop_app() -> None:
    adb_shell("am", "force-stop", PKG)


def launch_app() -> None:
    adb_shell("am", "start", "-n", f"{PKG}/.MainActivity")
    time.sleep(1.5)


def dismiss_system_popups() -> None:
    """Dismiss emulator promo popups (e.g. "Try out your stylus") if present.

    The Android 14+ stylus handwriting tutorial pops up the FIRST time you
    tap an EditText. Detect it by its title and click Cancel.
    """
    for _ in range(3):
        try:
            nodes = dump_ui()
        except Exception:
            return
        title = find_by_text(nodes, "Try out your stylus", contains=True)
        if title:
            cancel = find_by_text(nodes, "Cancel", contains=False)
            if cancel:
                print(f"  (dismissing stylus popup)")
                tap(cancel.cx, cancel.cy)
                time.sleep(0.8)
                continue
        # Generic dismiss buttons
        for label in ["No thanks", "Not now", "Dismiss", "Got it", "Skip"]:
            n = find_by_text(nodes, label, contains=False)
            if n:
                print(f"  (dismissing popup: {label!r})")
                tap(n.cx, n.cy)
                time.sleep(0.6)
                break
        else:
            return  # nothing to dismiss
    return


def log_step(label: str) -> None:
    print(f"\n--- {label} ---")


def assert_visible(text: str, *, contains: bool = True) -> bool:
    try:
        wait_for(text, contains=contains, timeout=5)
        print(f"  [OK] visible: {text!r}")
        return True
    except TimeoutError as exc:
        print(f"  [FAIL] not visible: {text!r}")
        return False


# ---- High-level flows -------------------------------------------------------

def login_as(email: str, password: str) -> None:
    log_step(f"Login as {email}")
    # Pre-cleanup: clear app data so we always start at Login (token might be cached from prior test).
    adb_shell("pm", "clear", PKG)
    launch_app()
    # Wait for login screen
    wait_for("Mock University", timeout=15)
    # Tap Email field, clear, type
    email_node = wait_for("Email", contains=False, timeout=5)
    tap(email_node.cx, email_node.cy + 70)  # tap just below the floating label, into the field
    time.sleep(0.6)
    dismiss_system_popups()
    clear_field()
    type_text(email)
    time.sleep(0.4)
    # Tap Password field
    pw_node = wait_for("Password", contains=False, timeout=5)
    tap(pw_node.cx, pw_node.cy + 70)
    time.sleep(0.6)
    dismiss_system_popups()
    clear_field()
    type_text(password)
    time.sleep(0.4)
    # Tap Sign in
    tap_text("Sign in", contains=False)
    # Wait for Home — the welcome heading
    wait_for("Welcome", contains=True, timeout=20)
    print("  [OK] logged in, Home is visible")


def open_chat() -> None:
    log_step("Open Chat")
    tap_text("Ask the assistant", contains=True)
    wait_for("Assistant", contains=True, timeout=10)
    print("  [OK] Chat screen open")


def send_chat(message: str, *, label: str, wait_route_text: str | None = None,
              wait_extra_s: int = 90) -> None:
    log_step(f"Send chat: {label}")
    dismiss_system_popups()
    placeholder = wait_for("Ask about classes", contains=True, timeout=8)
    tap(placeholder.cx, placeholder.cy)
    time.sleep(0.6)
    dismiss_system_popups()  # the stylus dialog might appear here
    clear_field()
    type_text(message)
    time.sleep(0.3)
    screenshot(f"chat_typed_{label}")
    tap_text("Send", contains=False)
    # Close the soft keyboard so dumps can see the conversation.
    adb_shell("input", "keyevent", "KEYCODE_BACK")
    time.sleep(0.4)
    # Poll for completion: wait until the "thinking" indicator is gone AND
    # a new "via " chip is visible.
    deadline = time.time() + wait_extra_s
    while time.time() < deadline:
        nodes = dump_ui()
        still_thinking = find_by_text(nodes, "thinking", contains=True)
        chip = find_by_text(nodes, "via ", contains=True)
        if not still_thinking and chip:
            break
        time.sleep(1.0)
    time.sleep(0.5)
    screenshot(f"chat_reply_{label}")


def navigate_back() -> None:
    """Tap the in-app 'Back' text button. Careful not to over-navigate:
    KEYCODE_BACK pops one screen at a time, and a second press from Home
    will exit the app to the launcher.
    """
    # Dump UI first. If we already see "Welcome" we're on Home — nothing to do.
    nodes = dump_ui()
    if find_by_text(nodes, "Welcome", contains=False):
        return
    # If an in-app 'Back' label is visible, tap it (TopAppBar back button).
    back_btn = find_by_text(nodes, "Back", contains=False)
    if back_btn:
        tap(back_btn.cx, back_btn.cy)
        time.sleep(0.6)
        return
    # Otherwise send one KEYCODE_BACK — typically just closes the keyboard
    # or pops one screen. Then re-check.
    adb_shell("input", "keyevent", "KEYCODE_BACK")
    time.sleep(0.6)
    nodes = dump_ui()
    if find_by_text(nodes, "Welcome", contains=False):
        return
    back_btn = find_by_text(nodes, "Back", contains=False)
    if back_btn:
        tap(back_btn.cx, back_btn.cy)
        time.sleep(0.6)


def open_tickets() -> None:
    log_step("Open Tickets")
    navigate_back()
    wait_for("Welcome", timeout=10)
    tap_text("My tickets", contains=True)
    wait_for("My tickets", contains=True, timeout=10)
    print("  [OK] Tickets screen open")


# ---- Suite runs -------------------------------------------------------------

def smoke() -> int:
    """Minimal coverage: login → chat 1 question → see reply → tickets list."""
    failures: list[str] = []

    def chk(passed: bool, label: str):
        if not passed:
            failures.append(label)

    login_as("bob@mock-university.edu", "password123")
    chk(assert_visible("Bob Patel"), "Home shows Bob Patel name")
    chk(assert_visible("Student #"),  "Home shows profile card")
    chk(assert_visible("Major"),       "Home shows Major")

    screenshot("home_bob")

    open_chat()
    send_chat("Please unlock my account, I can't log in.", label="bob_unlock")
    chk(assert_visible("via IT"), "Chat reply tagged 'via IT'")
    chk(assert_visible("View ticket"), "Chat shows ticket link")

    open_tickets()
    screenshot("tickets_bob")
    chk(assert_visible("IT Help Desk"), "Ticket list shows IT Help Desk")

    print("\n" + "=" * 50)
    if failures:
        print(f"SMOKE FAILED: {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SMOKE: all assertions passed.")
    return 0


def full_suite() -> int:
    """One representative query per category. Verifies the UI surfaces the
    'via DEPT' chip and (for ticket categories) the 'View ticket' link."""
    failures: list[str] = []

    def chk(passed: bool, label: str):
        mark = "OK" if passed else "FAIL"
        print(f"  [{mark}] {label}")
        if not passed:
            failures.append(label)

    print("\n========== Category 1: SMALLTALK ==========")
    login_as("alice@mock-university.edu", "password123")
    open_chat()
    send_chat("Thanks for your help!", label="cat1_smalltalk")
    chk(assert_visible("via GENERAL"), "smalltalk → via GENERAL chip")
    # No ticket-link assertion here: prior runs' chat history is still
    # rendered as bubbles after re-login, so a chat-wide search would be
    # noisy. The smalltalk path structurally cannot create tickets.

    print("\n========== Category 2: SINGLE-DEPT DIRECT ==========")
    # Already on Chat — send next message
    send_chat("What's my meal plan and dining balance?", label="cat2_single_direct")
    chk(assert_visible("via HOUSING"), "single_direct → via HOUSING chip")

    print("\n========== Category 3: MULTI-DEPT COMBINED ==========")
    send_chat("If I drop a math course, how does that affect my degree progress and my financial aid?",
              label="cat3_multi_combined", wait_extra_s=120)
    # Multi shows "via X + Y"
    chk(assert_visible("via ", contains=True), "multi_combined → chip visible")
    chk(assert_visible(" + ", contains=True), "multi_combined → '+' joiner in chip")

    print("\n========== Category 4: SINGLE-DEPT TICKET ==========")
    send_chat("Please open a Housing ticket on my behalf — I need to be moved out of North Hall room 214 due to a roommate conflict.",
              label="cat4_single_ticket")
    chk(assert_visible("via HOUSING"), "single_ticket → via HOUSING chip")
    chk(assert_visible("View ticket"), "single_ticket → View ticket link")

    print("\n========== Category 5: MULTI-DEPT TICKETS ==========")
    # Bob's account exercises this best (he has the holds we need)
    send_chat("I want to change my major to Mathematics and also need a new email alias from IT. Please set both up.",
              label="cat5_multi_ticket", wait_extra_s=180)
    chk(assert_visible(" + ", contains=True), "multi_ticket → '+' joiner in chip")
    # Multiple "View ticket" links should be present
    nodes = dump_ui()
    ticket_links = [n for n in nodes if "view ticket" in (n.text or n.desc or "").lower()]
    chk(len(ticket_links) >= 2, f"multi_ticket → ≥2 'View ticket' links (got {len(ticket_links)})")

    print("\n========== Tickets list ==========")
    open_tickets()
    screenshot("final_tickets")
    nodes = dump_ui()
    chk(find_by_text(nodes, "open", contains=False) is not None,
        "Tickets list shows at least one 'open' chip")

    print("\n" + "=" * 60)
    if failures:
        print(f"FULL SUITE: {len(failures)} failure(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("FULL SUITE: all assertions passed.")
    return 0


# ---- Entrypoint -------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["smoke", "full", "screenshot"], default="smoke", nargs="?")
    args = parser.parse_args()

    # Sanity-check the emulator is alive
    out = adb("devices").strip().splitlines()
    devices = [l for l in out[1:] if l.strip() and "device" in l]
    if not devices:
        print("ERROR: no emulator connected (run 'adb devices' to verify).")
        return 2
    print(f"Connected: {devices[0]}")

    if args.mode == "screenshot":
        path = screenshot(f"adhoc_{int(time.time())}")
        print(f"Wrote {path}")
        return 0
    if args.mode == "full":
        return full_suite()
    return smoke()


if __name__ == "__main__":
    sys.exit(main())
