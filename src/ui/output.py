"""
UI Output - Clean result output for commands.

This module provides:
- Summary panels for command results
- Progress spinners
- Tables for batch operations
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from typing import Dict, List, Optional
from contextlib import contextmanager

from src.ui.console import console, is_verbose


class FollowOutput:
    """
    Clean output for follow command.
    
    Default: Shows only summary (account, target, result, time)
    Verbose: Shows full step-by-step logs
    """
    
    @staticmethod
    def show_start(account: str, target: str):
        """Show follow operation starting."""
        if not is_verbose():
            console.print(f"\n  Following [bold]{target}[/] with [bold]{account}[/]...")
    
    @staticmethod
    def show_result(
        success: bool,
        account: str,
        target: str,
        duration: float,
        error: str = "",
        already_following: bool = False
    ):
        """Show follow result as clean summary."""
        
        # Build result table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim")
        table.add_column("Value")
        
        # Status
        if already_following:
            status = "⚡ Already Following"
            style = "yellow"
        elif success:
            status = "✓ Success"
            style = "green"
        else:
            status = "✗ Failed"
            style = "red"
        
        table.add_row("Status", f"[{style}]{status}[/{style}]")
        table.add_row("Account", account)
        table.add_row("Target", target)
        table.add_row("Duration", f"{duration:.2f}s")
        
        if error and not success:
            # Truncate long errors
            short_error = error[:50] + "..." if len(error) > 50 else error
            table.add_row("Error", f"[red]{short_error}[/red]")
        
        # Create panel
        title = "Follow Result"
        panel = Panel(table, title=title, border_style="dim")
        
        console.print(panel)
    
    @staticmethod
    @contextmanager
    def progress_spinner(message: str = "Working..."):
        """Show a spinner for operations."""
        if is_verbose():
            # In verbose mode, just print the message
            console.print(f"  {message}")
            yield
        else:
            # Show spinner
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True
            ) as progress:
                progress.add_task(description=message, total=None)
                yield


class BatchOutput:
    """
    Output for batch operations (multiple follows, creates).
    """
    
    @staticmethod
    def show_summary(
        operation: str,
        total: int,
        success: int,
        failed: int,
        duration: float,
        details: List[Dict] = None
    ):
        """Show batch operation summary."""
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim")
        table.add_column("Value")
        
        table.add_row("Total", str(total))
        table.add_row("Success", f"[green]{success}[/green]")
        table.add_row("Failed", f"[red]{failed}[/red]" if failed > 0 else "0")
        
        rate = (success / total * 100) if total > 0 else 0
        table.add_row("Success Rate", f"{rate:.1f}%")
        table.add_row("Duration", f"{duration:.2f}s")
        
        panel = Panel(table, title=f"{operation} Summary", border_style="dim")
        console.print(panel)
        
        # Show details if verbose and available
        if is_verbose() and details:
            detail_table = Table(show_header=True, box=None)
            detail_table.add_column("#", style="dim")
            detail_table.add_column("Account")
            detail_table.add_column("Result")
            
            for i, d in enumerate(details, 1):
                result = "[green]✓[/]" if d.get("success") else "[red]✗[/]"
                detail_table.add_row(str(i), d.get("account", "?"), result)
            
            console.print(detail_table)


# Convenience function for quick result display
def show_follow_result(**kwargs):
    """Quick wrapper for FollowOutput.show_result."""
    FollowOutput.show_result(**kwargs)
