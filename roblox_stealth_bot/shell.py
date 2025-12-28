"""
🖥️ Roblox Bot Interactive Shell
================================

نظام أوامر تفاعلي متقدم للتحكم بالبوت.

Features:
- Nested command contexts (accounts, proxies, system)
- Account inspection with follower counts
- System health monitoring
- Command history with persistence
- Auto-complete with descriptions
- Aliases and macros support
- Advanced error handling with suggestions

Usage:
    python cli.py shell
    python shell.py
"""

import os
import sys
import asyncio
import atexit
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

# Handle readline for Windows/Linux compatibility
try:
    import readline
    HAS_READLINE = True
except ImportError:
    try:
        import pyreadline3 as readline
        HAS_READLINE = True
    except ImportError:
        HAS_READLINE = False
        readline = None

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.live import Live
from rich.layout import Layout
from rich.style import Style


# =============================================================================
# CONFIGURATION
# =============================================================================

SHELL_VERSION = "1.0.0"
HISTORY_FILE = os.path.expanduser("~/.roblox_bot_history")
MAX_HISTORY_SIZE = 1000

# Command aliases
ALIASES = {
    'ls': 'list',
    'll': 'list',
    'q': 'exit',
    'quit': 'exit',
    'h': 'help',
    '?': 'help',
    'cls': 'clear',
    'c': 'clear',
    'b': 'back',
    's': 'status',
    'acc': 'accounts',
    'prx': 'proxies',
    'sys': 'system',
    'i': 'info',
    'ins': 'inspect',
}


# =============================================================================
# SHELL CONTEXT
# =============================================================================

@dataclass
class ShellContext:
    """Represents a command context/namespace."""
    name: str
    prompt_suffix: str
    commands: Dict[str, 'Command'] = field(default_factory=dict)
    parent: Optional['ShellContext'] = None
    description: str = ""


@dataclass  
class Command:
    """Represents a shell command."""
    name: str
    handler: Callable
    description: str
    usage: str = ""
    aliases: List[str] = field(default_factory=list)
    requires_args: bool = False
    arg_help: str = ""


# =============================================================================
# INSPECTOR - نظام التفتيش الشامل
# =============================================================================

class Inspector:
    """System inspection and health checking."""
    
    def __init__(self, console: Console):
        self.console = console
        self._init_database()
    
    def _init_database(self):
        """Initialize database connection."""
        try:
            from data.database import DatabaseManager, Account, Proxy, TaskLog, FollowRecord
            self.db = DatabaseManager()
            self.Account = Account
            self.Proxy = Proxy
            self.TaskLog = TaskLog
            self.FollowRecord = FollowRecord
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Database not available: {e}[/yellow]")
            self.db = None
    
    def inspect_account(self, username: str) -> bool:
        """Detailed inspection of a single account."""
        if not self.db:
            self.console.print("[red]Database not connected[/red]")
            return False
        
        try:
            account = self.Account.get_or_none(self.Account.username == username)
            if not account:
                self.console.print(f"[red]❌ Account '{username}' not found[/red]")
                self._suggest_similar_accounts(username)
                return False
            
            # Get follow records
            follows = list(self.FollowRecord.select().where(
                self.FollowRecord.account == account
            ).order_by(self.FollowRecord.followed_at.desc()).limit(20))
            
            # Build detailed report
            status_icon = "✅" if account.status == "active" else ("❌" if account.is_banned else "⚠️")
            gender_icon = "♂" if account.gender == 'male' else ("♀" if account.gender == 'female' else "❓")
            
            # Calculate account age
            age = datetime.now() - account.created_at
            age_str = f"{age.days}d {age.seconds // 3600}h" if age.days > 0 else f"{age.seconds // 3600}h {(age.seconds % 3600) // 60}m"
            
            # Last used
            if account.last_used:
                last_used_delta = datetime.now() - account.last_used
                last_used_str = f"{last_used_delta.days}d ago" if last_used_delta.days > 0 else f"{last_used_delta.seconds // 3600}h ago"
            else:
                last_used_str = "Never"
            
            # Health assessment
            health = self._assess_account_health(account)
            
            info_text = f"""[bold cyan]{account.username}[/bold cyan]

[bold]📋 Basic Info:[/bold]
  Status: {status_icon} {account.status}
  Gender: {gender_icon} {account.gender or 'Unknown'}
  Created: {account.created_at.strftime('%Y-%m-%d %H:%M')}
  Age: {age_str}
  Last Used: {last_used_str}

[bold]📊 Statistics:[/bold]
  Follows: [bold]{account.follow_count}[/bold] accounts followed
  Health: {health['icon']} {health['status']}
  
[bold]🔒 Security:[/bold]
  Banned: {'❌ Yes' if account.is_banned else '✅ No'}
  Cooldown: {account.cooldown_until.strftime('%H:%M') if account.cooldown_until and account.cooldown_until > datetime.now() else '✅ None'}
  
[bold]🌐 Technical:[/bold]
  Proxy: {account.proxy_used or 'None'}
  User Agent: {(account.user_agent[:50] + '...') if account.user_agent and len(account.user_agent) > 50 else account.user_agent or 'None'}
"""
            
            self.console.print(Panel(info_text, title=f"🔍 Account Inspection: {username}", border_style="cyan"))
            
            # Show follow history
            if follows:
                follow_table = Table(title=f"📋 Follow History ({len(follows)} shown)", box=None)
                follow_table.add_column("Target", style="cyan")
                follow_table.add_column("Date", style="dim")
                follow_table.add_column("Verified", justify="center")
                
                for f in follows[:10]:
                    follow_table.add_row(
                        f.target_username or f.target_id,
                        f.followed_at.strftime("%Y-%m-%d %H:%M"),
                        "✅" if f.verified else "❓"
                    )
                
                self.console.print(follow_table)
            
            # Notes
            if account.notes:
                self.console.print(Panel(account.notes, title="📝 Notes", border_style="yellow"))
            
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error inspecting account: {e}[/red]")
            return False
    
    def _assess_account_health(self, account) -> Dict[str, str]:
        """Assess account health status."""
        if account.is_banned:
            return {"status": "Banned", "icon": "🔴"}
        if account.status != "active":
            return {"status": "Inactive", "icon": "🟡"}
        if account.cooldown_until and account.cooldown_until > datetime.now():
            return {"status": "On Cooldown", "icon": "🟠"}
        if account.follow_count > 50:
            return {"status": "Heavy Usage", "icon": "🟡"}
        return {"status": "Good", "icon": "🟢"}
    
    def _suggest_similar_accounts(self, username: str):
        """Suggest similar account names."""
        try:
            accounts = list(self.Account.select().limit(100))
            similar = [a.username for a in accounts if username.lower() in a.username.lower()][:5]
            if similar:
                self.console.print(f"\n[dim]Did you mean: {', '.join(similar)}?[/dim]")
        except:
            pass
    
    def inspect_all_accounts(self) -> bool:
        """Full inspection of all accounts."""
        if not self.db:
            self.console.print("[red]Database not connected[/red]")
            return False
        
        try:
            accounts = list(self.Account.select().order_by(self.Account.created_at.desc()))
            
            if not accounts:
                self.console.print("[yellow]No accounts found. Create some first![/yellow]")
                return False
            
            # Summary stats
            total = len(accounts)
            active = sum(1 for a in accounts if a.status == 'active')
            banned = sum(1 for a in accounts if a.is_banned)
            male = sum(1 for a in accounts if a.gender == 'male')
            female = sum(1 for a in accounts if a.gender == 'female')
            total_follows = sum(a.follow_count for a in accounts)
            
            summary = Panel(
                f"[bold]Total:[/bold] {total} | "
                f"[green]Active:[/green] {active} | "
                f"[red]Banned:[/red] {banned} | "
                f"[blue]♂ Male:[/blue] {male} | "
                f"[magenta]♀ Female:[/magenta] {female} | "
                f"[cyan]Total Follows:[/cyan] {total_follows}",
                title="📊 Accounts Summary"
            )
            self.console.print(summary)
            
            # Detailed table
            table = Table(title=f"All Accounts ({total})")
            table.add_column("#", style="dim", width=4)
            table.add_column("Username", style="cyan")
            table.add_column("Status", width=10)
            table.add_column("Gender", width=8)
            table.add_column("Follows", justify="right", width=8)
            table.add_column("Health", width=12)
            table.add_column("Created", style="dim", width=12)
            
            for i, acc in enumerate(accounts, 1):
                status_style = "green" if acc.status == "active" else ("red" if acc.is_banned else "yellow")
                gender_icon = "♂" if acc.gender == 'male' else ("♀" if acc.gender == 'female' else "?")
                health = self._assess_account_health(acc)
                
                table.add_row(
                    str(i),
                    acc.username,
                    f"[{status_style}]{acc.status}[/{status_style}]",
                    f"{gender_icon} {acc.gender or '?'}",
                    str(acc.follow_count),
                    f"{health['icon']} {health['status']}",
                    acc.created_at.strftime("%m/%d %H:%M")
                )
            
            self.console.print(table)
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return False
    
    def inspect_proxies(self) -> bool:
        """Inspect proxy pool."""
        if not self.db:
            self.console.print("[red]Database not connected[/red]")
            return False
        
        try:
            proxies = list(self.Proxy.select().order_by(self.Proxy.latency_ms.asc()))
            
            if not proxies:
                self.console.print("[yellow]No proxies found[/yellow]")
                return False
            
            working = sum(1 for p in proxies if p.is_working)
            avg_latency = sum(p.latency_ms or 0 for p in proxies if p.is_working) / max(working, 1)
            
            summary = Panel(
                f"[bold]Total:[/bold] {len(proxies)} | "
                f"[green]Working:[/green] {working} | "
                f"[red]Failed:[/red] {len(proxies) - working} | "
                f"[cyan]Avg Latency:[/cyan] {avg_latency:.0f}ms",
                title="🌐 Proxy Pool Summary"
            )
            self.console.print(summary)
            
            table = Table(title="Proxy List")
            table.add_column("Server", style="cyan")
            table.add_column("Status", width=10)
            table.add_column("Latency", justify="right", width=10)
            table.add_column("Success", justify="right", width=8)
            table.add_column("Fails", justify="right", width=8)
            table.add_column("Source", style="dim")
            
            for proxy in proxies[:20]:
                status = "[green]✅ Working[/green]" if proxy.is_working else "[red]❌ Failed[/red]"
                latency = f"{proxy.latency_ms}ms" if proxy.latency_ms else "N/A"
                
                table.add_row(
                    proxy.server[:40],
                    status,
                    latency,
                    str(proxy.success_count),
                    str(proxy.fail_count),
                    proxy.source or "manual"
                )
            
            self.console.print(table)
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return False
    
    def inspect_system(self) -> bool:
        """Full system inspection."""
        if not self.db:
            self.console.print("[red]Database not connected[/red]")
            return False
        
        try:
            # Database stats
            account_stats = self.db.get_account_stats()
            proxy_stats = self.db.get_proxy_stats()
            task_stats = self.db.get_task_stats(hours=24)
            
            system_info = f"""[bold cyan]🖥️ System Status[/bold cyan]

[bold]📊 Accounts:[/bold]
  Total: {account_stats['total']}
  Active: [green]{account_stats['active']}[/green]
  Banned: [red]{account_stats['banned']}[/red]
  Total Follows: {account_stats['total_follows']}

[bold]🌐 Proxies:[/bold]
  Total: {proxy_stats['total']}
  Working: [green]{proxy_stats['working']}[/green]
  Failed: [red]{proxy_stats['failed']}[/red]
  Avg Latency: {proxy_stats['avg_latency_ms'] or 'N/A'}ms

[bold]📋 Tasks (24h):[/bold]
  Total: {task_stats['total']}
  Success: [green]{task_stats['success']}[/green]
  Failed: [red]{task_stats['failed']}[/red]
  Success Rate: {task_stats['success_rate']}%

[bold]🔧 System:[/bold]
  Shell Version: {SHELL_VERSION}
  Python: {sys.version.split()[0]}
  Database: ✅ Connected
"""
            
            self.console.print(Panel(system_info, title="🔍 Full System Inspection", border_style="cyan"))
            
            # Recent errors
            errors = self.db.get_recent_errors(limit=5)
            if errors:
                error_table = Table(title="⚠️ Recent Errors", border_style="red")
                error_table.add_column("Time", style="dim", width=16)
                error_table.add_column("Type", width=15)
                error_table.add_column("Error", style="red")
                
                for err in errors:
                    error_table.add_row(
                        err.timestamp.strftime("%m/%d %H:%M"),
                        err.task_type,
                        (err.error_message[:50] + "...") if len(err.error_message or "") > 50 else (err.error_message or "Unknown")
                    )
                
                self.console.print(error_table)
            
            return True
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return False


# =============================================================================
# MAIN SHELL CLASS
# =============================================================================

class BotShell:
    """Interactive command shell for the Roblox Bot."""
    
    def __init__(self):
        self.console = Console()
        self.running = True
        self.context_stack: List[ShellContext] = []
        self.inspector = Inspector(self.console)
        self.history: List[str] = []
        self.commander = None  # Lazy loaded
        
        # Setup contexts
        self._setup_contexts()
        self._setup_history()
    
    def _setup_history(self):
        """Setup command history with persistence."""
        if not HAS_READLINE or readline is None:
            return  # Skip history setup if readline not available
        
        try:
            if os.path.exists(HISTORY_FILE):
                readline.read_history_file(HISTORY_FILE)
            readline.set_history_length(MAX_HISTORY_SIZE)
            atexit.register(readline.write_history_file, HISTORY_FILE)
        except Exception:
            pass  # History is optional
        
        # Setup auto-complete
        try:
            readline.set_completer(self._completer)
            readline.parse_and_bind("tab: complete")
        except Exception:
            pass
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """Auto-complete handler."""
        current_context = self.context_stack[-1] if self.context_stack else self.main_context
        commands = list(current_context.commands.keys())
        
        # Add aliases
        for alias, cmd in ALIASES.items():
            if cmd in commands:
                commands.append(alias)
        
        matches = [c for c in commands if c.startswith(text)]
        
        try:
            return matches[state]
        except IndexError:
            return None
    
    def _setup_contexts(self):
        """Setup all command contexts."""
        
        # Main context
        self.main_context = ShellContext(
            name="main",
            prompt_suffix="",
            description="Main menu"
        )
        
        # Accounts context
        self.accounts_context = ShellContext(
            name="accounts",
            prompt_suffix="/accounts",
            parent=self.main_context,
            description="Account management"
        )
        
        # Proxies context
        self.proxies_context = ShellContext(
            name="proxies", 
            prompt_suffix="/proxies",
            parent=self.main_context,
            description="Proxy management"
        )
        
        # System context
        self.system_context = ShellContext(
            name="system",
            prompt_suffix="/system",
            parent=self.main_context,
            description="System monitoring"
        )
        
        # Register main commands
        self._register_main_commands()
        self._register_accounts_commands()
        self._register_proxies_commands()
        self._register_system_commands()
    
    def _register_main_commands(self):
        """Register main menu commands."""
        ctx = self.main_context
        
        ctx.commands['accounts'] = Command(
            name='accounts',
            handler=lambda args: self._enter_context(self.accounts_context),
            description='Enter accounts management',
            aliases=['acc']
        )
        
        ctx.commands['proxies'] = Command(
            name='proxies',
            handler=lambda args: self._enter_context(self.proxies_context),
            description='Enter proxy management',
            aliases=['prx']
        )
        
        ctx.commands['system'] = Command(
            name='system',
            handler=lambda args: self._enter_context(self.system_context),
            description='Enter system monitoring',
            aliases=['sys']
        )
        
        ctx.commands['create'] = Command(
            name='create',
            handler=self._cmd_create,
            description='Create new accounts',
            usage='create [count]',
            arg_help='count: Number of accounts (default: 1)'
        )
        
        ctx.commands['follow'] = Command(
            name='follow',
            handler=self._cmd_follow,
            description='Follow a user',
            usage='follow <target> [count]',
            requires_args=True,
            arg_help='target: Username or ID, count: Number of accounts'
        )
        
        ctx.commands['auto'] = Command(
            name='auto',
            handler=self._cmd_auto,
            description='Auto mode: create & follow',
            usage='auto <target> [accounts] [follows]',
            requires_args=True
        )
        
        ctx.commands['status'] = Command(
            name='status',
            handler=lambda args: self.inspector.inspect_system(),
            description='Quick system status',
            aliases=['s']
        )
        
        ctx.commands['help'] = Command(
            name='help',
            handler=self._cmd_help,
            description='Show help',
            aliases=['h', '?']
        )
        
        ctx.commands['clear'] = Command(
            name='clear',
            handler=lambda args: os.system('cls' if os.name == 'nt' else 'clear'),
            description='Clear screen',
            aliases=['cls', 'c']
        )
        
        ctx.commands['history'] = Command(
            name='history',
            handler=self._cmd_history,
            description='Show command history'
        )
        
        ctx.commands['exit'] = Command(
            name='exit',
            handler=self._cmd_exit,
            description='Exit shell',
            aliases=['quit', 'q']
        )
    
    def _register_accounts_commands(self):
        """Register accounts context commands."""
        ctx = self.accounts_context
        
        ctx.commands['list'] = Command(
            name='list',
            handler=lambda args: self.inspector.inspect_all_accounts(),
            description='List all accounts',
            aliases=['ls', 'll']
        )
        
        ctx.commands['info'] = Command(
            name='info',
            handler=self._cmd_account_info,
            description='Show account details',
            usage='info <username>',
            requires_args=True,
            aliases=['i']
        )
        
        ctx.commands['inspect'] = Command(
            name='inspect',
            handler=lambda args: self.inspector.inspect_all_accounts(),
            description='Full account inspection',
            aliases=['ins']
        )
        
        ctx.commands['health'] = Command(
            name='health',
            handler=self._cmd_health_check,
            description='Run health check'
        )
        
        ctx.commands['back'] = Command(
            name='back',
            handler=lambda args: self._exit_context(),
            description='Return to main menu',
            aliases=['b']
        )
        
        ctx.commands['help'] = Command(
            name='help',
            handler=self._cmd_help,
            description='Show help',
            aliases=['h', '?']
        )
        
        ctx.commands['exit'] = Command(
            name='exit',
            handler=self._cmd_exit,
            description='Exit shell',
            aliases=['quit', 'q']
        )
    
    def _register_proxies_commands(self):
        """Register proxies context commands."""
        ctx = self.proxies_context
        
        ctx.commands['list'] = Command(
            name='list',
            handler=lambda args: self.inspector.inspect_proxies(),
            description='List all proxies',
            aliases=['ls']
        )
        
        ctx.commands['stats'] = Command(
            name='stats',
            handler=lambda args: self.inspector.inspect_proxies(),
            description='Proxy statistics'
        )
        
        ctx.commands['refresh'] = Command(
            name='refresh',
            handler=self._cmd_refresh_proxies,
            description='Refresh proxy pool'
        )
        
        ctx.commands['back'] = Command(
            name='back',
            handler=lambda args: self._exit_context(),
            description='Return to main menu',
            aliases=['b']
        )
        
        ctx.commands['help'] = Command(
            name='help',
            handler=self._cmd_help,
            description='Show help'
        )
        
        ctx.commands['exit'] = Command(
            name='exit',
            handler=self._cmd_exit,
            description='Exit shell',
            aliases=['quit', 'q']
        )
    
    def _register_system_commands(self):
        """Register system context commands."""
        ctx = self.system_context
        
        ctx.commands['status'] = Command(
            name='status',
            handler=lambda args: self.inspector.inspect_system(),
            description='Full system status',
            aliases=['s']
        )
        
        ctx.commands['tasks'] = Command(
            name='tasks',
            handler=self._cmd_tasks,
            description='Recent task history'
        )
        
        ctx.commands['errors'] = Command(
            name='errors',
            handler=self._cmd_errors,
            description='Recent errors'
        )
        
        ctx.commands['config'] = Command(
            name='config',
            handler=self._cmd_config,
            description='Show configuration'
        )
        
        ctx.commands['back'] = Command(
            name='back',
            handler=lambda args: self._exit_context(),
            description='Return to main menu',
            aliases=['b']
        )
        
        ctx.commands['help'] = Command(
            name='help',
            handler=self._cmd_help,
            description='Show help'
        )
        
        ctx.commands['exit'] = Command(
            name='exit',
            handler=self._cmd_exit,
            description='Exit shell',
            aliases=['quit', 'q']
        )
    
    # =========================================================================
    # COMMAND HANDLERS
    # =========================================================================
    
    def _cmd_help(self, args: List[str]):
        """Show help for current context."""
        current = self.context_stack[-1] if self.context_stack else self.main_context
        
        table = Table(title=f"📖 Available Commands ({current.name})", border_style="blue")
        table.add_column("Command", style="cyan", width=15)
        table.add_column("Aliases", style="dim", width=12)
        table.add_column("Description")
        table.add_column("Usage", style="dim")
        
        for cmd in current.commands.values():
            aliases = ", ".join(cmd.aliases) if cmd.aliases else "-"
            table.add_row(cmd.name, aliases, cmd.description, cmd.usage or "-")
        
        self.console.print(table)
        
        self.console.print("\n[dim]💡 Tips:[/dim]")
        self.console.print("[dim]  • Use Tab for auto-complete[/dim]")
        self.console.print("[dim]  • Use ↑↓ for command history[/dim]")
        self.console.print("[dim]  • Aliases work anywhere (e.g., 'ls' = 'list')[/dim]")
    
    def _cmd_history(self, args: List[str]):
        """Show command history."""
        table = Table(title="📜 Command History (last 20)")
        table.add_column("#", style="dim", width=5)
        table.add_column("Command", style="cyan")
        
        if HAS_READLINE and readline:
            try:
                history_len = readline.get_current_history_length()
                start = max(0, history_len - 20)
                
                for i in range(start, history_len):
                    cmd = readline.get_history_item(i + 1)
                    if cmd:
                        table.add_row(str(i + 1), cmd)
                
                self.console.print(table)
                return
            except Exception:
                pass
        
        # Fallback to internal history
        if self.history:
            for i, cmd in enumerate(self.history[-20:], 1):
                table.add_row(str(i), cmd)
            self.console.print(table)
        else:
            self.console.print("[yellow]No history available[/yellow]")
    
    def _cmd_exit(self, args: List[str]):
        """Exit the shell."""
        self.console.print("\n[bold cyan]👋 Goodbye! Stay stealthy![/bold cyan]\n")
        self.running = False
    
    def _cmd_account_info(self, args: List[str]):
        """Show account info."""
        if not args:
            self.console.print("[yellow]Usage: info <username>[/yellow]")
            return
        self.inspector.inspect_account(args[0])
    
    def _cmd_health_check(self, args: List[str]):
        """Run health check."""
        self.console.print("[bold]🔍 Running health check...[/bold]\n")
        try:
            from data.database import Account
            import datetime
            
            for account in Account.select():
                icon = "✅" if not account.is_banned else "❌"
                health = self.inspector._assess_account_health(account)
                self.console.print(f"  {icon} {account.username}: {health['icon']} {health['status']}")
                account.last_health_check = datetime.datetime.now()
                account.save()
            
            self.console.print("\n[dim]Health check complete[/dim]")
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _cmd_refresh_proxies(self, args: List[str]):
        """Refresh proxy pool."""
        self.console.print("[bold]🔄 Refreshing proxies...[/bold]")
        self.console.print("[yellow]Feature coming soon![/yellow]")
    
    def _cmd_tasks(self, args: List[str]):
        """Show recent tasks."""
        try:
            from data.database import TaskLog
            
            tasks = list(TaskLog.select().order_by(TaskLog.timestamp.desc()).limit(15))
            
            if not tasks:
                self.console.print("[yellow]No tasks found[/yellow]")
                return
            
            table = Table(title="📋 Recent Tasks")
            table.add_column("Time", style="dim", width=16)
            table.add_column("Type", width=15)
            table.add_column("Status", width=12)
            table.add_column("Target", style="cyan")
            table.add_column("Duration", justify="right", width=10)
            
            for task in tasks:
                status_style = "green" if task.status == "success" else "red"
                duration = f"{task.duration_seconds:.1f}s" if task.duration_seconds else "-"
                
                table.add_row(
                    task.timestamp.strftime("%m/%d %H:%M"),
                    task.task_type,
                    f"[{status_style}]{task.status}[/{status_style}]",
                    task.target or "-",
                    duration
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _cmd_errors(self, args: List[str]):
        """Show recent errors."""
        try:
            from data.database import DatabaseManager
            
            db = DatabaseManager()
            errors = db.get_recent_errors(limit=10)
            
            if not errors:
                self.console.print("[green]✅ No recent errors![/green]")
                return
            
            table = Table(title="⚠️ Recent Errors", border_style="red") 
            table.add_column("Time", style="dim", width=16)
            table.add_column("Type", width=15)
            table.add_column("Error", style="red")
            
            for err in errors:
                table.add_row(
                    err.timestamp.strftime("%m/%d %H:%M"),
                    err.task_type,
                    err.error_message or "Unknown error"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _cmd_config(self, args: List[str]):
        """Show configuration."""
        try:
            import yaml
            
            config_path = "config/config.yaml"
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                
                self.console.print(Panel(
                    yaml.dump(config, default_flow_style=False, allow_unicode=True),
                    title="⚙️ Configuration",
                    border_style="blue"
                ))
            else:
                self.console.print("[yellow]Config file not found[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _cmd_create(self, args: List[str]):
        """Create accounts."""
        count = int(args[0]) if args else 1
        self.console.print(f"[bold]📝 Creating {count} account(s)...[/bold]")
        
        async def run():
            from src.control.commander import Commander
            commander = Commander(headless=True)
            try:
                await commander.initialize()
                result = await commander.create_accounts(count)
                self.console.print(f"[green]✅ Created: {result.completed}[/green] | [red]❌ Failed: {result.failed}[/red]")
            finally:
                await commander.shutdown()
        
        try:
            asyncio.run(run())
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _cmd_follow(self, args: List[str]):
        """Follow a user.
        
        Usage: follow <target> [count] [--verbose]
        """
        # Parse --verbose flag
        verbose = "--verbose" in args or "-v" in args
        args = [a for a in args if a not in ("--verbose", "-v")]
        
        if not args:
            self.console.print("[yellow]Usage: follow <target> [count] [--verbose][/yellow]")
            return
        
        target = args[0]
        count = int(args[1]) if len(args) > 1 else 1
        
        # Import and set verbose mode
        from src.ui import set_verbose, FollowOutput
        set_verbose(verbose)
        
        # Show start message (only in non-verbose mode)
        if not verbose:
            FollowOutput.show_start("auto-select", target)
        else:
            self.console.print(f"[bold]👥 Following {target} with {count} account(s)...[/bold]")
        
        async def run():
            import time
            start_time = time.time()
            
            from src.control.commander import Commander
            commander = Commander(headless=True)
            try:
                await commander.initialize()
                result = await commander.follow_user(target, count, target.isdigit())
                
                duration = time.time() - start_time
                
                # Show clean result panel
                if count == 1:
                    # Single follow - show detailed result
                    FollowOutput.show_result(
                        success=result.completed > 0,
                        account=getattr(result, 'account_used', 'unknown'),
                        target=target,
                        duration=duration,
                        error=getattr(result, 'error', ''),
                        already_following=getattr(result, 'already_following', False)
                    )
                else:
                    # Batch follow - show summary
                    from src.ui import BatchOutput
                    BatchOutput.show_summary(
                        operation="Follow",
                        total=count,
                        success=result.completed,
                        failed=result.failed,
                        duration=duration
                    )
            finally:
                await commander.shutdown()
        
        try:
            asyncio.run(run())
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
    
    def _cmd_auto(self, args: List[str]):
        """Auto mode."""
        if not args:
            self.console.print("[yellow]Usage: auto <target> [accounts] [follows][/yellow]")
            return
        
        target = args[0]
        accounts = int(args[1]) if len(args) > 1 else 5
        follows = int(args[2]) if len(args) > 2 else 1
        
        self.console.print(Panel(
            f"Target: {target}\nAccounts to create: {accounts}\nFollows per account: {follows}",
            title="🚀 Auto Mode"
        ))
        
        self.console.print("[yellow]Running auto mode...[/yellow]")
        # Implementation similar to CLI auto command
    
    # =========================================================================
    # CONTEXT NAVIGATION
    # =========================================================================
    
    def _enter_context(self, context: ShellContext):
        """Enter a sub-context."""
        self.context_stack.append(context)
        self.console.print(f"[dim]→ Entering {context.name}...[/dim]")
    
    def _exit_context(self):
        """Exit current context."""
        if self.context_stack:
            exited = self.context_stack.pop()
            self.console.print(f"[dim]← Leaving {exited.name}...[/dim]")
        else:
            self.console.print("[dim]Already at main menu[/dim]")
    
    def _get_prompt(self) -> str:
        """Build the current prompt string."""
        if self.context_stack:
            path = "/".join(c.name for c in self.context_stack)
            return f"\n[bold cyan]bot/{path}>[/bold cyan] "
        return "\n[bold cyan]bot>[/bold cyan] "
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    def _show_banner(self):
        """Show welcome banner."""
        banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🤖  [bold cyan]ROBLOX BOT - Interactive Shell[/bold cyan]  🤖           ║
║                                                           ║
║   [dim]Version {version} | Type 'help' for commands[/dim]           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""".format(version=SHELL_VERSION)
        
        self.console.print(banner)
        
        # Quick stats
        try:
            from data.database import Account, Proxy
            accounts = Account.select().count()
            active = Account.select().where(Account.status == 'active').count()
            proxies = Proxy.select().where(Proxy.is_working == True).count()
            self.console.print(f"[dim]📊 Accounts: {accounts} ({active} active) | 🌐 Proxies: {proxies} working[/dim]\n")
        except:
            pass
    
    def _process_command(self, raw_input: str):
        """Process a command string."""
        raw_input = raw_input.strip()
        if not raw_input:
            return
        
        # Save to history
        self.history.append(raw_input)
        
        # Parse command and args
        parts = raw_input.split()
        cmd_name = parts[0].lower()
        args = parts[1:]
        
        # Check aliases
        if cmd_name in ALIASES:
            cmd_name = ALIASES[cmd_name]
        
        # Get current context
        current = self.context_stack[-1] if self.context_stack else self.main_context
        
        # Find command
        if cmd_name in current.commands:
            cmd = current.commands[cmd_name]
            
            # Check required args
            if cmd.requires_args and not args:
                self.console.print(f"[yellow]Usage: {cmd.usage}[/yellow]")
                if cmd.arg_help:
                    self.console.print(f"[dim]{cmd.arg_help}[/dim]")
                return
            
            try:
                cmd.handler(args)
            except Exception as e:
                self.console.print(f"[red]❌ Error: {e}[/red]")
                self._suggest_fix(cmd_name, str(e))
        else:
            self.console.print(f"[red]❌ Unknown command: '{cmd_name}'[/red]")
            self._suggest_command(cmd_name, current)
    
    def _suggest_command(self, cmd_name: str, context: ShellContext):
        """Suggest similar commands."""
        commands = list(context.commands.keys())
        similar = [c for c in commands if c.startswith(cmd_name[0]) or cmd_name in c][:3]
        if similar:
            self.console.print(f"[dim]Did you mean: {', '.join(similar)}?[/dim]")
        self.console.print("[dim]Type 'help' for available commands[/dim]")
    
    def _suggest_fix(self, cmd_name: str, error: str):
        """Suggest fixes for common errors."""
        if "database" in error.lower():
            self.console.print("[dim]💡 Try running 'python cli.py init' first[/dim]")
        elif "connection" in error.lower():
            self.console.print("[dim]💡 Check your internet connection[/dim]")
    
    def run(self):
        """Main shell loop."""
        self._show_banner()
        
        while self.running:
            try:
                prompt = self._get_prompt()
                user_input = self.console.input(prompt)
                self._process_command(user_input)
                
            except KeyboardInterrupt:
                self.console.print("\n[dim]Use 'exit' or 'q' to quit[/dim]")
            except EOFError:
                self._cmd_exit([])


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Entry point for the shell."""
    shell = BotShell()
    shell.run()


if __name__ == '__main__':
    main()
