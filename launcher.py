"""PyInstaller entry point; the frozen demo worker does not open a window."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo-worker":
        if sys.stdout is None:
            sys.stdout = open(sys.argv[3] + ".stdout", "w", encoding="utf-8")
            sys.stderr = sys.stdout
        from resources.demo_worker import main
        raise SystemExit(main(sys.argv[2:]))
    if len(sys.argv) > 2 and sys.argv[1] == "--self-test":
        from pathlib import Path
        from changelens.smoke import run
        raise SystemExit(run(Path(sys.argv[2])))
    if len(sys.argv)>2 and sys.argv[1]=='--self-test-languages':
        from pathlib import Path
        from changelens.polyglot_smoke import run
        raise SystemExit(run(Path(sys.argv[2])))
    if len(sys.argv)>2 and sys.argv[1]=='--self-test-format':
        from pathlib import Path
        from changelens.format_smoke import run
        raise SystemExit(run(Path(sys.argv[2])))
    if len(sys.argv)>2 and sys.argv[1]=='--self-test-workflow':
        from pathlib import Path
        from changelens.refinement_smoke import run
        raise SystemExit(run(Path(sys.argv[2])))
    if len(sys.argv)>2 and sys.argv[1]=='--self-test-architecture':
        from pathlib import Path
        from changelens.architecture_smoke import run
        raise SystemExit(run(Path(sys.argv[2])))
    if len(sys.argv)>2 and sys.argv[1]=='--self-test-focus':
        from pathlib import Path
        from changelens.focus_smoke import run
        raise SystemExit(run(Path(sys.argv[2])))
    from changelens.workbench import main
    main()
