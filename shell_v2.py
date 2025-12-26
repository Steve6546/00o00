"""
🖥️ Roblox Bot Interactive Shell v2.0
=====================================

نظام أوامر تفاعلي متقدم مع:
- Auto-complete ذكي مع أوصاف عربية
- التنقل بالأسهم ↑↓
- اقتراحات فورية أثناء الكتابة
- تاريخ الأوامر

Usage:
    python shell_v2.py
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style


# =============================================================================
# الأوامر مع الأوصاف العربية
# =============================================================================

COMMANDS_AR = {
    # القائمة الرئيسية
    'main': {
        'help':     {'ar': '📖 عرض المساعدة', 'en': 'Show help'},
        'accounts': {'ar': '👤 دخول إدارة الحسابات', 'en': 'Enter accounts management'},
        'system':   {'ar': '🖥️ دخول مراقبة النظام', 'en': 'Enter system monitoring'},
        'proxies':  {'ar': '🌐 دخول إدارة البروكسي', 'en': 'Enter proxy management'},
        'status':   {'ar': '📊 عرض حالة النظام السريعة', 'en': 'Quick system status'},
        'create':   {'ar': '✨ إنشاء حسابات جديدة', 'en': 'Create new accounts'},
        'follow':   {'ar': '👥 متابعة مستخدم', 'en': 'Follow a user'},
        'auto':     {'ar': '🚀 الوضع التلقائي (إنشاء + متابعة)', 'en': 'Auto mode'},
        'history':  {'ar': '📜 عرض تاريخ الأوامر', 'en': 'Command history'},
        'clear':    {'ar': '🧹 مسح الشاشة', 'en': 'Clear screen'},
        'exit':     {'ar': '👋 خروج من البرنامج', 'en': 'Exit program'},
    },
    # قائمة الحسابات
    'accounts': {
        'list':    {'ar': '📋 عرض جميع الحسابات', 'en': 'List all accounts'},
        'info':    {'ar': '🔍 تفاصيل حساب معين', 'en': 'Account details'},
        'health':  {'ar': '💚 فحص صحة الحسابات', 'en': 'Health check'},
        'inspect': {'ar': '🔎 تفتيش شامل للحسابات', 'en': 'Full inspection'},
        'back':    {'ar': '⬅️ رجوع للقائمة الرئيسية', 'en': 'Go back'},
        'help':    {'ar': '📖 عرض المساعدة', 'en': 'Show help'},
        'exit':    {'ar': '👋 خروج من البرنامج', 'en': 'Exit program'},
    },
    # قائمة النظام
    'system': {
        'status':  {'ar': '📊 حالة النظام الكاملة', 'en': 'Full system status'},
        'tasks':   {'ar': '📋 عرض المهام الأخيرة', 'en': 'Recent tasks'},
        'errors':  {'ar': '⚠️ عرض الأخطاء الأخيرة', 'en': 'Recent errors'},
        'config':  {'ar': '⚙️ عرض الإعدادات', 'en': 'Show configuration'},
        'back':    {'ar': '⬅️ رجوع للقائمة الرئيسية', 'en': 'Go back'},
        'help':    {'ar': '📖 عرض المساعدة', 'en': 'Show help'},
        'exit':    {'ar': '👋 خروج من البرنامج', 'en': 'Exit program'},
    },
    # قائمة البروكسي
    'proxies': {
        'list':    {'ar': '📋 عرض جميع البروكسيات', 'en': 'List all proxies'},
        'stats':   {'ar': '📊 إحصائيات البروكسي', 'en': 'Proxy statistics'},
        'refresh': {'ar': '🔄 تحديث قائمة البروكسي', 'en': 'Refresh proxies'},
        'back':    {'ar': '⬅️ رجوع للقائمة الرئيسية', 'en': 'Go back'},
        'help':    {'ar': '📖 عرض المساعدة', 'en': 'Show help'},
        'exit':    {'ar': '👋 خروج من البرنامج', 'en': 'Exit program'},
    },
}

# الاختصارات
ALIASES = {
    'ls': 'list', 'll': 'list',
    'q': 'exit', 'quit': 'exit',
    'h': 'help', '?': 'help',
    'cls': 'clear', 'c': 'clear',
    'b': 'back',
    's': 'status',
    'acc': 'accounts',
    'prx': 'proxies',
    'sys': 'system',
    'i': 'info',
}

# الستايل
SHELL_STYLE = Style.from_dict({
    'completion-menu.completion': 'bg:#333333 #ffffff',
    'completion-menu.completion.current': 'bg:#00aa00 #ffffff bold',
    'completion-menu.meta.completion': 'bg:#444444 #aaaaaa',
    'completion-menu.meta.completion.current': 'bg:#00aa00 #ffffff',
    'prompt': '#00ff00 bold',
})


# =============================================================================
# المُكمِّل الذكي
# =============================================================================

class ArabicCompleter(Completer):
    """Auto-completer with Arabic descriptions."""
    
    def __init__(self, shell):
        self.shell = shell
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lower()
        word = document.get_word_before_cursor()
        
        # الحصول على الأوامر للسياق الحالي
        context = self.shell.current_context
        commands = COMMANDS_AR.get(context, COMMANDS_AR['main'])
        
        # إضافة الاختصارات
        all_commands = {}
        for cmd, desc in commands.items():
            all_commands[cmd] = desc
        for alias, cmd in ALIASES.items():
            if cmd in commands:
                all_commands[alias] = {'ar': f'↪️ اختصار لـ {cmd}', 'en': f'Alias for {cmd}'}
        
        # تصفية الأوامر
        for cmd, desc in all_commands.items():
            if cmd.startswith(word.lower()) or not word:
                yield Completion(
                    cmd,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=desc['ar']  # الوصف بالعربي
                )


# =============================================================================
# الـ Shell المحسن
# =============================================================================

class EnhancedBotShell:
    """Interactive shell with smart auto-complete."""
    
    def __init__(self):
        self.console = Console()
        self.running = True
        self.current_context = 'main'
        self.context_stack = []
        
        # Setup prompt with auto-complete
        self.session = PromptSession(
            history=FileHistory(os.path.expanduser('~/.roblox_bot_history')),
            auto_suggest=AutoSuggestFromHistory(),
            completer=ArabicCompleter(self),
            style=SHELL_STYLE,
            complete_while_typing=True,
        )
        
        # Initialize inspector
        self._init_inspector()
    
    def _init_inspector(self):
        """Initialize the inspector for database operations."""
        try:
            from data.database import DatabaseManager, Account, Proxy, TaskLog, FollowRecord
            self.db = DatabaseManager()
            self.Account = Account
            self.Proxy = Proxy
            self.TaskLog = TaskLog
            self.FollowRecord = FollowRecord
            self.db_connected = True
        except Exception as e:
            self.db = None
            self.db_connected = False
    
    def _get_prompt(self) -> str:
        """Build prompt string."""
        if self.current_context == 'main':
            return 'bot> '
        return f'bot/{self.current_context}> '
    
    def _show_banner(self):
        """Show welcome banner."""
        banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🤖  ROBLOX BOT - Interactive Shell v2.0  🤖            ║
║                                                           ║
║   ℹ️  اكتب أي حرف لترى الاقتراحات                        ║
║   ⬆️⬇️ استخدم الأسهم للتنقل                               ║
║   ↵  اضغط Enter للاختيار                                 ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
        self.console.print(banner, style="cyan")
        
        # Quick stats
        try:
            accounts = self.Account.select().count()
            active = self.Account.select().where(self.Account.status == 'active').count()
            proxies = self.Proxy.select().where(self.Proxy.is_working == True).count()
            self.console.print(f"[dim]📊 الحسابات: {accounts} ({active} نشط) | 🌐 البروكسي: {proxies} يعمل[/dim]\n")
        except:
            pass
    
    def _show_help(self):
        """Show help for current context."""
        commands = COMMANDS_AR.get(self.current_context, COMMANDS_AR['main'])
        
        table = Table(title=f"📖 الأوامر المتاحة ({self.current_context})", border_style="blue")
        table.add_column("الأمر", style="cyan", width=12)
        table.add_column("الوصف", style="white")
        table.add_column("الاختصار", style="dim", width=8)
        
        for cmd, desc in commands.items():
            # Find alias
            alias = next((a for a, c in ALIASES.items() if c == cmd), "-")
            table.add_row(cmd, desc['ar'], alias)
        
        self.console.print(table)
        self.console.print("\n[dim]💡 نصائح:[/dim]")
        self.console.print("[dim]  • اكتب أي حرف لترى الاقتراحات[/dim]")
        self.console.print("[dim]  • استخدم ⬆️⬇️ للتنقل بين الاقتراحات[/dim]")
        self.console.print("[dim]  • اضغط Tab للإكمال التلقائي[/dim]")
    
    def _enter_context(self, context: str):
        """Enter a sub-context."""
        self.context_stack.append(self.current_context)
        self.current_context = context
        self.console.print(f"[dim]→ دخول {context}...[/dim]")
    
    def _exit_context(self):
        """Exit current context."""
        if self.context_stack:
            self.current_context = self.context_stack.pop()
            self.console.print(f"[dim]← رجوع...[/dim]")
        else:
            self.current_context = 'main'
    
    def _show_accounts(self):
        """Show all accounts."""
        if not self.db_connected:
            self.console.print("[red]❌ قاعدة البيانات غير متصلة[/red]")
            return
        
        try:
            accounts = list(self.Account.select().order_by(self.Account.created_at.desc()))
            
            if not accounts:
                self.console.print("[yellow]لا توجد حسابات. استخدم 'create' لإنشاء حسابات جديدة[/yellow]")
                return
            
            # Summary
            total = len(accounts)
            active = sum(1 for a in accounts if a.status == 'active')
            banned = sum(1 for a in accounts if a.is_banned)
            
            self.console.print(Panel(
                f"[bold]المجموع:[/bold] {total} | "
                f"[green]نشط:[/green] {active} | "
                f"[red]محظور:[/red] {banned}",
                title="📊 ملخص الحسابات"
            ))
            
            table = Table(title=f"جميع الحسابات ({total})")
            table.add_column("#", style="dim", width=4)
            table.add_column("اسم المستخدم", style="cyan")
            table.add_column("الحالة", width=10)
            table.add_column("المتابعات", justify="right", width=8)
            table.add_column("الصحة", width=12)
            
            for i, acc in enumerate(accounts, 1):
                status_style = "green" if acc.status == "active" else ("red" if acc.is_banned else "yellow")
                health_icon = "🟢" if acc.status == "active" and not acc.is_banned else ("🔴" if acc.is_banned else "🟡")
                
                table.add_row(
                    str(i),
                    acc.username,
                    f"[{status_style}]{acc.status}[/{status_style}]",
                    str(acc.follow_count),
                    f"{health_icon} {'جيد' if acc.status == 'active' else 'تحذير'}"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]خطأ: {e}[/red]")
    
    def _show_system_status(self):
        """Show system status."""
        if not self.db_connected:
            self.console.print("[red]❌ قاعدة البيانات غير متصلة[/red]")
            return
        
        try:
            account_stats = self.db.get_account_stats()
            proxy_stats = self.db.get_proxy_stats()
            task_stats = self.db.get_task_stats(hours=24)
            
            info = f"""[bold cyan]🖥️ حالة النظام[/bold cyan]

[bold]📊 الحسابات:[/bold]
  المجموع: {account_stats['total']}
  نشط: [green]{account_stats['active']}[/green]
  محظور: [red]{account_stats['banned']}[/red]
  إجمالي المتابعات: {account_stats['total_follows']}

[bold]🌐 البروكسي:[/bold]
  المجموع: {proxy_stats['total']}
  يعمل: [green]{proxy_stats['working']}[/green]
  فشل: [red]{proxy_stats['failed']}[/red]

[bold]📋 المهام (24 ساعة):[/bold]
  المجموع: {task_stats['total']}
  نجاح: [green]{task_stats['success']}[/green]
  فشل: [red]{task_stats['failed']}[/red]
  نسبة النجاح: {task_stats['success_rate']}%
"""
            self.console.print(Panel(info, title="🔍 تفتيش النظام الكامل", border_style="cyan"))
        except Exception as e:
            self.console.print(f"[red]خطأ: {e}[/red]")
    
    def _show_tasks(self):
        """Show recent tasks."""
        try:
            tasks = list(self.TaskLog.select().order_by(self.TaskLog.timestamp.desc()).limit(10))
            
            if not tasks:
                self.console.print("[yellow]لا توجد مهام[/yellow]")
                return
            
            table = Table(title="📋 المهام الأخيرة")
            table.add_column("الوقت", style="dim", width=16)
            table.add_column("النوع", width=15)
            table.add_column("الحالة", width=10)
            
            for task in tasks:
                status_style = "green" if task.status == "success" else "red"
                table.add_row(
                    task.timestamp.strftime("%m/%d %H:%M"),
                    task.task_type,
                    f"[{status_style}]{task.status}[/{status_style}]"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]خطأ: {e}[/red]")
    
    def _show_errors(self):
        """Show recent errors."""
        try:
            errors = self.db.get_recent_errors(limit=10)
            if not errors:
                self.console.print("[green]✅ لا توجد أخطاء حديثة![/green]")
                return
            
            table = Table(title="⚠️ الأخطاء الأخيرة", border_style="red")
            table.add_column("الوقت", style="dim", width=16)
            table.add_column("النوع", width=15)
            table.add_column("الخطأ", style="red")
            
            for err in errors:
                table.add_row(
                    err.timestamp.strftime("%m/%d %H:%M"),
                    err.task_type,
                    err.error_message or "غير معروف"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]خطأ: {e}[/red]")
    
    def _show_proxies(self):
        """Show proxies."""
        if not self.db_connected:
            self.console.print("[red]❌ قاعدة البيانات غير متصلة[/red]")
            return
        
        try:
            proxies = list(self.Proxy.select().order_by(self.Proxy.latency_ms.asc()))
            
            if not proxies:
                self.console.print("[yellow]لا يوجد بروكسي[/yellow]")
                return
            
            working = sum(1 for p in proxies if p.is_working)
            
            self.console.print(Panel(
                f"[bold]المجموع:[/bold] {len(proxies)} | "
                f"[green]يعمل:[/green] {working} | "
                f"[red]فشل:[/red] {len(proxies) - working}",
                title="🌐 ملخص البروكسي"
            ))
            
            table = Table(title="قائمة البروكسي")
            table.add_column("الخادم", style="cyan")
            table.add_column("الحالة", width=10)
            table.add_column("السرعة", justify="right", width=10)
            
            for proxy in proxies[:15]:
                status = "[green]✅ يعمل[/green]" if proxy.is_working else "[red]❌ فشل[/red]"
                latency = f"{proxy.latency_ms}ms" if proxy.latency_ms else "N/A"
                table.add_row(proxy.server[:40], status, latency)
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]خطأ: {e}[/red]")
    
    def _health_check(self):
        """Run health check."""
        self.console.print("[bold]🔍 جاري فحص الصحة...[/bold]\n")
        try:
            for account in self.Account.select():
                icon = "✅" if not account.is_banned else "❌"
                health = "🟢 جيد" if account.status == "active" else ("🔴 محظور" if account.is_banned else "🟡 غير نشط")
                self.console.print(f"  {icon} {account.username}: {health}")
                account.last_health_check = datetime.now()
                account.save()
            self.console.print("\n[dim]تم فحص الصحة[/dim]")
        except Exception as e:
            self.console.print(f"[red]خطأ: {e}[/red]")
    
    def _process_command(self, cmd: str):
        """Process a command."""
        cmd = cmd.strip().lower()
        if not cmd:
            return
        
        # Check aliases
        parts = cmd.split()
        cmd_name = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd_name in ALIASES:
            cmd_name = ALIASES[cmd_name]
        
        # Main context
        if self.current_context == 'main':
            if cmd_name == 'help':
                self._show_help()
            elif cmd_name == 'accounts':
                self._enter_context('accounts')
            elif cmd_name == 'system':
                self._enter_context('system')
            elif cmd_name == 'proxies':
                self._enter_context('proxies')
            elif cmd_name == 'status':
                self._show_system_status()
            elif cmd_name == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
            elif cmd_name == 'exit':
                self.console.print("\n[bold cyan]👋 مع السلامة![/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ أمر غير معروف: '{cmd_name}'[/red]")
                self.console.print("[dim]اكتب 'help' لعرض الأوامر المتاحة[/dim]")
        
        # Accounts context
        elif self.current_context == 'accounts':
            if cmd_name == 'list':
                self._show_accounts()
            elif cmd_name == 'health':
                self._health_check()
            elif cmd_name == 'inspect':
                self._show_accounts()
            elif cmd_name == 'help':
                self._show_help()
            elif cmd_name == 'back':
                self._exit_context()
            elif cmd_name == 'exit':
                self.console.print("\n[bold cyan]👋 مع السلامة![/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ أمر غير معروف: '{cmd_name}'[/red]")
        
        # System context
        elif self.current_context == 'system':
            if cmd_name == 'status':
                self._show_system_status()
            elif cmd_name == 'tasks':
                self._show_tasks()
            elif cmd_name == 'errors':
                self._show_errors()
            elif cmd_name == 'help':
                self._show_help()
            elif cmd_name == 'back':
                self._exit_context()
            elif cmd_name == 'exit':
                self.console.print("\n[bold cyan]👋 مع السلامة![/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ أمر غير معروف: '{cmd_name}'[/red]")
        
        # Proxies context
        elif self.current_context == 'proxies':
            if cmd_name == 'list' or cmd_name == 'stats':
                self._show_proxies()
            elif cmd_name == 'help':
                self._show_help()
            elif cmd_name == 'back':
                self._exit_context()
            elif cmd_name == 'exit':
                self.console.print("\n[bold cyan]👋 مع السلامة![/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ أمر غير معروف: '{cmd_name}'[/red]")
    
    def run(self):
        """Main shell loop."""
        self._show_banner()
        
        while self.running:
            try:
                user_input = self.session.prompt(self._get_prompt())
                self._process_command(user_input)
            except KeyboardInterrupt:
                self.console.print("\n[dim]اكتب 'exit' للخروج[/dim]")
            except EOFError:
                self.running = False


# =============================================================================
# Entry Point
# =============================================================================

def main():
    shell = EnhancedBotShell()
    shell.run()


if __name__ == '__main__':
    main()
