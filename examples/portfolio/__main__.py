from pathlib import Path
from tempfile import TemporaryDirectory

from examples.portfolio.demo import render_demo

if __name__ == "__main__":
    with TemporaryDirectory(prefix="agentshield-portfolio-") as directory:
        print(render_demo("gdpr-broker", Path(directory) / "runtime.db"))
