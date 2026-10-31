"""Retry Tk initialization when the graphical display is not ready yet."""

import sys
import time
import tkinter as tk


DISPLAY_RETRY_INTERVAL_SECONDS = 2
DISPLAY_RETRY_COUNT = 30
DISPLAY_ERROR_MARKERS = (
    "couldn't connect to display",
    "could not connect to display",
    "cannot open display",
    "no display name",
)


def create_tk_root():
    for retry in range(DISPLAY_RETRY_COUNT + 1):
        try:
            return tk.Tk()
        except tk.TclError as error:
            if not any(marker in str(error).casefold() for marker in DISPLAY_ERROR_MARKERS):
                raise
            if retry == DISPLAY_RETRY_COUNT:
                raise
            print(
                f"Tkinter could not connect to the display ({error}). "
                f"Retrying in {DISPLAY_RETRY_INTERVAL_SECONDS} seconds "
                f"({retry + 1}/{DISPLAY_RETRY_COUNT}).",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(DISPLAY_RETRY_INTERVAL_SECONDS)
