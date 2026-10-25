"""Entry point of the installed JobHunter.exe (built by installer/build.ps1).

One exe does everything, so the installed app needs no Python:
  JobHunter.exe              the window (gui.py)
  JobHunter.exe --bot ...    a bot run, with bot.py's own options (used by the window and Auto-run)
  JobHunter.exe --cv ...     build a CV or cover letter PDF (used by bot.py)

From source, keep using python -I gui.py / bot.py / cv.py.
"""
import io
import os
import sys


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("--bot", "--cv") else None
    if mode:
        del sys.argv[1]  # bot.py and cv.py read their own options from sys.argv
    # A windowed exe has no console. The window reads the bot's output through a pipe, in UTF-8;
    # Auto-run has nowhere to write it, and runs.log keeps the summary anyway.
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        elif isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if mode == "--bot":
        import bot
        bot.main()
    elif mode == "--cv":
        import cv
        cv.main()
    else:
        import gui
        gui.App().mainloop()


if __name__ == "__main__":
    main()
