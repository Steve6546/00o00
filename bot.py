"""
🖥️ Roblox Bot Professional Shell
=================================

نظام أوامر تفاعلي احترافي مع:
- دعم اللغة العربية والإنجليزية
- التبديل بين اللغات
- Auto-complete ذكي
- واجهة احترافية

Usage:
    python bot.py
    python bot.py --lang ar
    python bot.py --lang en
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings


# =============================================================================
# CONFIGURATION
# =============================================================================

VERSION = "3.0.0"
HISTORY_FILE = os.path.expanduser("~/.roblox_bot_history")

# Style
SHELL_STYLE = Style.from_dict({
    'completion-menu.completion': 'bg:#1a1a2e #ffffff',
    'completion-menu.completion.current': 'bg:#0f3460 #e94560 bold',
    'completion-menu.meta.completion': 'bg:#16213e #7f8c8d',
    'completion-menu.meta.completion.current': 'bg:#0f3460 #ffffff',
    'prompt': '#00ff00 bold',
})


# =============================================================================
# TRANSLATIONS / الترجمات
# =============================================================================

LANG = {
    'ar': {
        'shell_name': 'Roblox Bot',
        'welcome': 'مرحبا بك في نظام التحكم',
        'type_help': 'اكتب / لعرض الأوامر',
        'arrows_hint': 'استخدم الأسهم للتنقل',
        'enter_hint': 'اضغط Enter للاختيار',
        'accounts_count': 'الحسابات',
        'active': 'نشط',
        'proxies': 'البروكسي',
        'working': 'يعمل',
        'unknown_cmd': 'أمر غير معروف',
        'type_help_hint': 'اكتب / لعرض الأوامر',
        'goodbye': 'مع السلامة!',
        'entering': 'دخول',
        'leaving': 'خروج',
        'available_commands': 'الأوامر المتاحة',
        'command': 'الأمر',
        'shortcut': 'اختصار',
        'description': 'الوصف',
        'tips': 'نصائح',
        'tip_slash': 'اكتب / لعرض جميع الأوامر',
        'tip_arrows': 'استخدم الأسهم للتنقل',
        'tip_tab': 'اضغط Tab للإكمال',
        'tip_lang': 'اكتب lang en للإنجليزية',
        'no_accounts': 'لا توجد حسابات',
        'create_hint': 'استخدم create لإنشاء حسابات',
        'accounts_summary': 'ملخص الحسابات',
        'total': 'المجموع',
        'banned': 'محظور',
        'all_accounts': 'جميع الحسابات',
        'username': 'اسم المستخدم',
        'status': 'الحالة',
        'follows': 'المتابعات',
        'health': 'الصحة',
        'good': 'جيد',
        'warning': 'تحذير',
        'system_status': 'حالة النظام',
        'recent_tasks': 'المهام الأخيرة',
        'recent_errors': 'الأخطاء الأخيرة',
        'no_tasks': 'لا توجد مهام',
        'no_errors': 'لا توجد أخطاء',
        'no_proxies': 'لا يوجد بروكسي',
        'proxy_summary': 'ملخص البروكسي',
        'failed': 'فشل',
        'proxy_list': 'قائمة البروكسي',
        'server': 'الخادم',
        'speed': 'السرعة',
        'health_check': 'فحص الصحة',
        'health_complete': 'تم الفحص',
        'db_error': 'خطأ في قاعدة البيانات',
        'time': 'الوقت',
        'type': 'النوع',
        'error': 'الخطأ',
        # Commands
        'cmd_help': 'عرض المساعدة',
        'cmd_accounts': 'إدارة الحسابات',
        'cmd_system': 'مراقبة النظام',
        'cmd_proxies': 'إدارة البروكسي',
        'cmd_status': 'حالة النظام السريعة',
        'cmd_create': 'إنشاء حسابات جديدة',
        'cmd_follow': 'متابعة مستخدم',
        'cmd_auto': 'الوضع التلقائي',
        'cmd_clear': 'مسح الشاشة',
        'cmd_lang': 'تبديل اللغة',
        'cmd_exit': 'خروج',
        'cmd_list': 'عرض القائمة',
        'cmd_info': 'تفاصيل حساب',
        'cmd_health': 'فحص الصحة',
        'cmd_back': 'رجوع',
        'cmd_tasks': 'المهام الأخيرة',
        'cmd_errors': 'الأخطاء الأخيرة',
        'cmd_config': 'الإعدادات',
        'cmd_stats': 'الإحصائيات',
        'cmd_refresh': 'تحديث القائمة',
    },
    'en': {
        'shell_name': 'Roblox Bot',
        'welcome': 'Welcome to Control System',
        'type_help': 'Type / to show commands',
        'arrows_hint': 'Use arrows to navigate',
        'enter_hint': 'Press Enter to select',
        'accounts_count': 'Accounts',
        'active': 'active',
        'proxies': 'Proxies',
        'working': 'working',
        'unknown_cmd': 'Unknown command',
        'type_help_hint': 'Type / to show commands',
        'goodbye': 'Goodbye!',
        'entering': 'Entering',
        'leaving': 'Leaving',
        'available_commands': 'Available Commands',
        'command': 'Command',
        'shortcut': 'Shortcut',
        'description': 'Description',
        'tips': 'Tips',
        'tip_slash': 'Type / to show all commands',
        'tip_arrows': 'Use arrows to navigate',
        'tip_tab': 'Press Tab to complete',
        'tip_lang': 'Type lang ar for Arabic',
        'no_accounts': 'No accounts found',
        'create_hint': 'Use create to add accounts',
        'accounts_summary': 'Accounts Summary',
        'total': 'Total',
        'banned': 'Banned',
        'all_accounts': 'All Accounts',
        'username': 'Username',
        'status': 'Status',
        'follows': 'Follows',
        'health': 'Health',
        'good': 'Good',
        'warning': 'Warning',
        'system_status': 'System Status',
        'recent_tasks': 'Recent Tasks',
        'recent_errors': 'Recent Errors',
        'no_tasks': 'No tasks found',
        'no_errors': 'No errors found',
        'no_proxies': 'No proxies found',
        'proxy_summary': 'Proxy Summary',
        'failed': 'Failed',
        'proxy_list': 'Proxy List',
        'server': 'Server',
        'speed': 'Speed',
        'health_check': 'Health Check',
        'health_complete': 'Check complete',
        'db_error': 'Database error',
        'time': 'Time',
        'type': 'Type',
        'error': 'Error',
        # Commands
        'cmd_help': 'Show help',
        'cmd_accounts': 'Account management',
        'cmd_system': 'System monitoring',
        'cmd_proxies': 'Proxy management',
        'cmd_status': 'Quick system status',
        'cmd_create': 'Create new accounts',
        'cmd_follow': 'Follow a user',
        'cmd_auto': 'Auto mode',
        'cmd_clear': 'Clear screen',
        'cmd_lang': 'Switch language',
        'cmd_exit': 'Exit program',
        'cmd_list': 'Show list',
        'cmd_info': 'Account details',
        'cmd_health': 'Health check',
        'cmd_back': 'Go back',
        'cmd_tasks': 'Recent tasks',
        'cmd_errors': 'Recent errors',
        'cmd_config': 'Configuration',
        'cmd_stats': 'Statistics',
        'cmd_refresh': 'Refresh list',
    }
}

# Commands per context
COMMANDS = {
    'main': ['help', 'accounts', 'system', 'proxies', 'status', 'create', 'follow', 'auto', 'clear', 'lang', 'exit'],
    'accounts': ['list', 'info', 'health', 'back', 'help', 'exit'],
    'system': ['status', 'tasks', 'errors', 'config', 'back', 'help', 'exit'],
    'proxies': ['list', 'stats', 'refresh', 'back', 'help', 'exit'],
}

# Shortcuts
SHORTCUTS = {
    'help': 'h', 'accounts': 'acc', 'system': 'sys', 'proxies': 'prx',
    'status': 's', 'exit': 'q', 'list': 'ls', 'back': 'b', 'clear': 'cls',
}


# =============================================================================
# SMART COMPLETER
# =============================================================================

class SmartCompleter(Completer):
    """Auto-completer with bilingual support."""
    
    def __init__(self, shell):
        self.shell = shell
    
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lower().strip()
        
        # Show all commands when typing / or -
        show_all = text in ['/', '-', ''] or text.startswith('/') or text.startswith('-')
        
        # Get word
        word = text.lstrip('/-')
        
        # Get commands for current context
        context = self.shell.current_context
        commands = COMMANDS.get(context, COMMANDS['main'])
        
        lang = self.shell.lang
        
        for cmd in commands:
            if show_all or cmd.startswith(word) or not word:
                # Get description
                desc_key = f'cmd_{cmd}'
                desc = LANG[lang].get(desc_key, cmd)
                
                # Get shortcut
                shortcut = SHORTCUTS.get(cmd, '')
                if shortcut:
                    display = f"{cmd}"
                    meta = f"{desc} [{shortcut}]"
                else:
                    display = cmd
                    meta = desc
                
                yield Completion(
                    cmd,
                    start_position=-len(word) if word else 0,
                    display=display,
                    display_meta=meta
                )
        
        # Add shortcuts
        for shortcut, cmd in SHORTCUTS.items():
            if cmd in commands and (show_all or shortcut.startswith(word)):
                desc_key = f'cmd_{cmd}'
                desc = LANG[lang].get(desc_key, cmd)
                
                yield Completion(
                    shortcut,
                    start_position=-len(word) if word else 0,
                    display=f"{shortcut}",
                    display_meta=f"-> {cmd}"
                )


# =============================================================================
# PROFESSIONAL SHELL
# =============================================================================

class ProfessionalShell:
    """Professional bilingual interactive shell."""
    
    def __init__(self, lang: str = 'en'):
        self.console = Console()
        self.running = True
        self.lang = lang
        self.current_context = 'main'
        self.context_stack = []
        
        # Setup prompt
        self.session = PromptSession(
            history=FileHistory(HISTORY_FILE),
            auto_suggest=AutoSuggestFromHistory(),
            completer=SmartCompleter(self),
            style=SHELL_STYLE,
            complete_while_typing=True,
        )
        
        # Initialize database
        self._init_db()
    
    def t(self, key: str) -> str:
        """Get translated string."""
        return LANG[self.lang].get(key, key)
    
    def _init_db(self):
        """Initialize database connection."""
        try:
            from data.database import DatabaseManager, Account, Proxy, TaskLog, FollowRecord
            self.db = DatabaseManager()
            self.Account = Account
            self.Proxy = Proxy
            self.TaskLog = TaskLog
            self.FollowRecord = FollowRecord
            self.db_connected = True
        except:
            self.db = None
            self.db_connected = False
    
    def _get_prompt(self) -> str:
        """Build prompt string."""
        if self.current_context == 'main':
            return 'bot> '
        return f'bot/{self.current_context}> '
    
    def _show_banner(self):
        """Show welcome banner."""
        # Clear screen first
        os.system('cls' if os.name == 'nt' else 'clear')
        
        banner_lines = [
            "",
            "╔═══════════════════════════════════════════════════════════╗",
            "║                                                           ║",
            f"║   🤖  {self.t('shell_name')} - Professional Shell v{VERSION}  🤖      ║",
            "║                                                           ║",
            f"║   ℹ️  {self.t('type_help'):<43} ║",
            f"║   ⬆️⬇️ {self.t('arrows_hint'):<43} ║",
            f"║   ↵  {self.t('enter_hint'):<44} ║",
            "║                                                           ║",
            "╚═══════════════════════════════════════════════════════════╝",
            "",
        ]
        
        for line in banner_lines:
            self.console.print(line, style="cyan")
        
        # Quick stats
        try:
            if self.db_connected:
                accounts = self.Account.select().count()
                active = self.Account.select().where(self.Account.status == 'active').count()
                proxies = self.Proxy.select().where(self.Proxy.is_working == True).count()
                
                stats = f"📊 {self.t('accounts_count')}: {accounts} ({active} {self.t('active')}) | 🌐 {self.t('proxies')}: {proxies} {self.t('working')}"
                self.console.print(f"[dim]{stats}[/dim]")
                self.console.print()
        except:
            pass
    
    def _show_help(self):
        """Show help for current context."""
        commands = COMMANDS.get(self.current_context, COMMANDS['main'])
        
        table = Table(title=f"📖 {self.t('available_commands')} ({self.current_context})", border_style="blue")
        table.add_column(self.t('command'), style="cyan", width=12)
        table.add_column(self.t('shortcut'), style="dim", width=8)
        table.add_column(self.t('description'), style="white")
        
        for cmd in commands:
            desc_key = f'cmd_{cmd}'
            desc = self.t(desc_key)
            shortcut = SHORTCUTS.get(cmd, '-')
            table.add_row(cmd, shortcut, desc)
        
        self.console.print(table)
        self.console.print()
        self.console.print(f"[dim]💡 {self.t('tips')}:[/dim]")
        self.console.print(f"[dim]  • {self.t('tip_slash')}[/dim]")
        self.console.print(f"[dim]  • {self.t('tip_arrows')}[/dim]")
        self.console.print(f"[dim]  • {self.t('tip_tab')}[/dim]")
        self.console.print(f"[dim]  • {self.t('tip_lang')}[/dim]")
    
    def _enter_context(self, context: str):
        """Enter a sub-context."""
        self.context_stack.append(self.current_context)
        self.current_context = context
        self.console.print(f"[dim]→ {self.t('entering')} {context}...[/dim]")
    
    def _exit_context(self):
        """Exit current context."""
        if self.context_stack:
            old = self.current_context
            self.current_context = self.context_stack.pop()
            self.console.print(f"[dim]← {self.t('leaving')} {old}...[/dim]")
        else:
            self.current_context = 'main'
    
    def _show_accounts(self):
        """Show all accounts."""
        if not self.db_connected:
            self.console.print(f"[red]❌ {self.t('db_error')}[/red]")
            return
        
        try:
            accounts = list(self.Account.select().order_by(self.Account.created_at.desc()))
            
            if not accounts:
                self.console.print(f"[yellow]{self.t('no_accounts')}. {self.t('create_hint')}[/yellow]")
                return
            
            # Summary
            total = len(accounts)
            active = sum(1 for a in accounts if a.status == 'active')
            banned = sum(1 for a in accounts if a.is_banned)
            
            self.console.print(Panel(
                f"[bold]{self.t('total')}:[/bold] {total} | "
                f"[green]{self.t('active')}:[/green] {active} | "
                f"[red]{self.t('banned')}:[/red] {banned}",
                title=f"📊 {self.t('accounts_summary')}"
            ))
            
            table = Table(title=f"{self.t('all_accounts')} ({total})")
            table.add_column("#", style="dim", width=4)
            table.add_column(self.t('username'), style="cyan")
            table.add_column(self.t('status'), width=10)
            table.add_column(self.t('follows'), justify="right", width=8)
            table.add_column(self.t('health'), width=10)
            
            for i, acc in enumerate(accounts, 1):
                status_style = "green" if acc.status == "active" else ("red" if acc.is_banned else "yellow")
                health_icon = "🟢" if acc.status == "active" and not acc.is_banned else ("🔴" if acc.is_banned else "🟡")
                health_text = self.t('good') if acc.status == "active" else self.t('warning')
                
                table.add_row(
                    str(i),
                    acc.username,
                    f"[{status_style}]{acc.status}[/{status_style}]",
                    str(acc.follow_count),
                    f"{health_icon} {health_text}"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]{self.t('error')}: {e}[/red]")
    
    def _show_system_status(self):
        """Show system status."""
        if not self.db_connected:
            self.console.print(f"[red]❌ {self.t('db_error')}[/red]")
            return
        
        try:
            account_stats = self.db.get_account_stats()
            proxy_stats = self.db.get_proxy_stats()
            task_stats = self.db.get_task_stats(hours=24)
            
            info = f"""[bold cyan]🖥️ {self.t('system_status')}[/bold cyan]

[bold]📊 {self.t('accounts_count')}:[/bold]
  {self.t('total')}: {account_stats['total']}
  {self.t('active')}: [green]{account_stats['active']}[/green]
  {self.t('banned')}: [red]{account_stats['banned']}[/red]
  {self.t('follows')}: {account_stats['total_follows']}

[bold]🌐 {self.t('proxies')}:[/bold]
  {self.t('total')}: {proxy_stats['total']}
  {self.t('working')}: [green]{proxy_stats['working']}[/green]
  {self.t('failed')}: [red]{proxy_stats['failed']}[/red]
"""
            self.console.print(Panel(info, title=f"🔍 {self.t('system_status')}", border_style="cyan"))
        except Exception as e:
            self.console.print(f"[red]{self.t('error')}: {e}[/red]")
    
    def _show_tasks(self):
        """Show recent tasks."""
        try:
            tasks = list(self.TaskLog.select().order_by(self.TaskLog.timestamp.desc()).limit(10))
            
            if not tasks:
                self.console.print(f"[yellow]{self.t('no_tasks')}[/yellow]")
                return
            
            table = Table(title=f"📋 {self.t('recent_tasks')}")
            table.add_column(self.t('time'), style="dim", width=16)
            table.add_column(self.t('type'), width=15)
            table.add_column(self.t('status'), width=10)
            
            for task in tasks:
                status_style = "green" if task.status == "success" else "red"
                table.add_row(
                    task.timestamp.strftime("%m/%d %H:%M"),
                    task.task_type,
                    f"[{status_style}]{task.status}[/{status_style}]"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]{self.t('error')}: {e}[/red]")
    
    def _show_errors(self):
        """Show recent errors."""
        try:
            errors = self.db.get_recent_errors(limit=10)
            if not errors:
                self.console.print(f"[green]✅ {self.t('no_errors')}![/green]")
                return
            
            table = Table(title=f"⚠️ {self.t('recent_errors')}", border_style="red")
            table.add_column(self.t('time'), style="dim", width=16)
            table.add_column(self.t('type'), width=15)
            table.add_column(self.t('error'), style="red")
            
            for err in errors:
                table.add_row(
                    err.timestamp.strftime("%m/%d %H:%M"),
                    err.task_type,
                    err.error_message or "Unknown"
                )
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]{self.t('error')}: {e}[/red]")
    
    def _show_proxies(self):
        """Show proxies."""
        if not self.db_connected:
            self.console.print(f"[red]❌ {self.t('db_error')}[/red]")
            return
        
        try:
            proxies = list(self.Proxy.select().order_by(self.Proxy.latency_ms.asc()))
            
            if not proxies:
                self.console.print(f"[yellow]{self.t('no_proxies')}[/yellow]")
                return
            
            working = sum(1 for p in proxies if p.is_working)
            
            self.console.print(Panel(
                f"[bold]{self.t('total')}:[/bold] {len(proxies)} | "
                f"[green]{self.t('working')}:[/green] {working} | "
                f"[red]{self.t('failed')}:[/red] {len(proxies) - working}",
                title=f"🌐 {self.t('proxy_summary')}"
            ))
            
            table = Table(title=self.t('proxy_list'))
            table.add_column(self.t('server'), style="cyan")
            table.add_column(self.t('status'), width=10)
            table.add_column(self.t('speed'), justify="right", width=10)
            
            for proxy in proxies[:15]:
                status = f"[green]✅ {self.t('working')}[/green]" if proxy.is_working else f"[red]❌ {self.t('failed')}[/red]"
                latency = f"{proxy.latency_ms}ms" if proxy.latency_ms else "N/A"
                table.add_row(proxy.server[:40], status, latency)
            
            self.console.print(table)
        except Exception as e:
            self.console.print(f"[red]{self.t('error')}: {e}[/red]")
    
    def _health_check(self):
        """Run health check."""
        self.console.print(f"[bold]🔍 {self.t('health_check')}...[/bold]\n")
        try:
            for account in self.Account.select():
                icon = "✅" if not account.is_banned else "❌"
                health = f"🟢 {self.t('good')}" if account.status == "active" else (f"🔴 {self.t('banned')}" if account.is_banned else f"🟡 {self.t('warning')}")
                self.console.print(f"  {icon} {account.username}: {health}")
                account.last_health_check = datetime.now()
                account.save()
            self.console.print(f"\n[dim]{self.t('health_complete')}[/dim]")
        except Exception as e:
            self.console.print(f"[red]{self.t('error')}: {e}[/red]")
    
    def _switch_language(self, new_lang: str):
        """Switch language."""
        if new_lang in ['ar', 'en']:
            self.lang = new_lang
            self._show_banner()
        else:
            self.console.print("[yellow]Usage: lang ar | lang en[/yellow]")
    
    def _process_command(self, cmd: str):
        """Process a command."""
        cmd = cmd.strip().lower().lstrip('/-')
        if not cmd:
            return
        
        parts = cmd.split()
        cmd_name = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        # Check shortcuts
        for full, short in SHORTCUTS.items():
            if cmd_name == short:
                cmd_name = full
                break
        
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
            elif cmd_name == 'lang':
                if args:
                    self._switch_language(args[0])
                else:
                    self.console.print("[yellow]Usage: lang ar | lang en[/yellow]")
            elif cmd_name == 'exit':
                self.console.print(f"\n[bold cyan]👋 {self.t('goodbye')}[/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ {self.t('unknown_cmd')}: '{cmd_name}'[/red]")
                self.console.print(f"[dim]{self.t('type_help_hint')}[/dim]")
        
        # Accounts context
        elif self.current_context == 'accounts':
            if cmd_name == 'list':
                self._show_accounts()
            elif cmd_name == 'health':
                self._health_check()
            elif cmd_name == 'help':
                self._show_help()
            elif cmd_name == 'back':
                self._exit_context()
            elif cmd_name == 'exit':
                self.console.print(f"\n[bold cyan]👋 {self.t('goodbye')}[/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ {self.t('unknown_cmd')}: '{cmd_name}'[/red]")
        
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
                self.console.print(f"\n[bold cyan]👋 {self.t('goodbye')}[/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ {self.t('unknown_cmd')}: '{cmd_name}'[/red]")
        
        # Proxies context
        elif self.current_context == 'proxies':
            if cmd_name == 'list' or cmd_name == 'stats':
                self._show_proxies()
            elif cmd_name == 'help':
                self._show_help()
            elif cmd_name == 'back':
                self._exit_context()
            elif cmd_name == 'exit':
                self.console.print(f"\n[bold cyan]👋 {self.t('goodbye')}[/bold cyan]\n")
                self.running = False
            else:
                self.console.print(f"[red]❌ {self.t('unknown_cmd')}: '{cmd_name}'[/red]")
    
    def run(self):
        """Main shell loop."""
        self._show_banner()
        
        while self.running:
            try:
                user_input = self.session.prompt(self._get_prompt())
                self._process_command(user_input)
            except KeyboardInterrupt:
                self.console.print(f"\n[dim]{self.t('type_help_hint')}[/dim]")
            except EOFError:
                self.running = False


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Roblox Bot Professional Shell')
    parser.add_argument('--lang', '-l', choices=['ar', 'en'], default='en', help='Language (ar/en)')
    args = parser.parse_args()
    
    shell = ProfessionalShell(lang=args.lang)
    shell.run()


if __name__ == '__main__':
    main()
