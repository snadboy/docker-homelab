#!/usr/bin/env python3
"""
Sample script using the 'rich' library.
Displays formatted system information with colors and tables.
"""

import platform
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

def main():
    console = Console(force_terminal=True)

    # Header panel
    console.print(Panel.fit(
        "[bold blue]System Information Report[/bold blue]\n"
        f"[dim]Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        border_style="blue"
    ))
    console.print()

    # System info table
    sys_table = Table(title="System Details", box=box.ROUNDED)
    sys_table.add_column("Property", style="cyan", no_wrap=True)
    sys_table.add_column("Value", style="green")

    sys_table.add_row("Platform", platform.system())
    sys_table.add_row("Platform Release", platform.release())
    sys_table.add_row("Platform Version", platform.version()[:50] + "...")
    sys_table.add_row("Architecture", platform.machine())
    sys_table.add_row("Hostname", platform.node())
    sys_table.add_row("Python Version", platform.python_version())
    sys_table.add_row("Python Impl", platform.python_implementation())

    console.print(sys_table)
    console.print()

    # Environment variables table
    env_table = Table(title="Key Environment Variables", box=box.ROUNDED)
    env_table.add_column("Variable", style="yellow", no_wrap=True)
    env_table.add_column("Value", style="white")

    important_vars = ['HOME', 'USER', 'PATH', 'VIRTUAL_ENV', 'PYTHONPATH', 'TZ']
    for var in important_vars:
        value = os.environ.get(var, '[not set]')
        # Truncate long values
        if len(value) > 60:
            value = value[:57] + "..."
        env_table.add_row(var, value)

    console.print(env_table)
    console.print()

    # Success message
    console.print("[bold green]Script completed successfully![/bold green]")

    return 0

if __name__ == "__main__":
    exit(main())
