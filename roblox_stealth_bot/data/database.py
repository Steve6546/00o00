from peewee import *
import datetime
import os

db_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(db_dir, 'bot.db')
db = SqliteDatabase(db_path)


class BaseModel(Model):
    class Meta:
        database = db


class Proxy(BaseModel):
    server = CharField(unique=True)
    username = CharField(null=True)
    password = CharField(null=True)
    last_checked = DateTimeField(default=datetime.datetime.now)
    is_working = BooleanField(default=True)
    latency_ms = IntegerField(null=True)
    fail_count = IntegerField(default=0)
    success_count = IntegerField(default=0)
    source = CharField(null=True)


class Account(BaseModel):
    username = CharField(unique=True)
    password = CharField()
    birthday = DateField()
    gender = CharField(null=True)
    cookie = TextField(null=True)
    user_agent = TextField(null=True)
    proxy_used = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    last_used = DateTimeField(null=True)
    cooldown_until = DateTimeField(null=True)
    status = CharField(default="active")  # active, banned, cooldown, suspicious
    follow_count = IntegerField(default=0)
    notes = TextField(null=True)


class TaskLog(BaseModel):
    task_type = CharField()  # account_creation, follow, login, etc.
    target = CharField(null=True)
    status = CharField()  # success, failed, captcha_blocked, etc.
    error_message = TextField(null=True)
    timestamp = DateTimeField(default=datetime.datetime.now)
    duration_seconds = FloatField(null=True)
    account = ForeignKeyField(Account, backref='logs', null=True)
    proxy_used = CharField(null=True)


class FollowRecord(BaseModel):
    """Track which accounts have followed which targets."""
    account = ForeignKeyField(Account, backref='follow_records')
    target_id = CharField()  # Target user ID
    followed_at = DateTimeField(default=datetime.datetime.now)
    verified = BooleanField(default=False)
    
    class Meta:
        indexes = ((('account', 'target_id'), True),)  # Unique together


class DatabaseManager:
    """Enhanced database manager with tracking and statistics."""
    
    def __init__(self):
        self.connect()

    def connect(self):
        db.connect(reuse_if_open=True)
        db.create_tables([Proxy, Account, TaskLog, FollowRecord])

    def close(self):
        if not db.is_closed():
            db.close()
    
    # ===== Follow Tracking =====
    
    def has_followed(self, account_id: int, target_id: str) -> bool:
        """Check if account has already followed target."""
        return FollowRecord.select().where(
            (FollowRecord.account == account_id) &
            (FollowRecord.target_id == target_id)
        ).exists()
    
    def record_follow(self, account_id: int, target_id: str, verified: bool = True):
        """Record a follow action."""
        return FollowRecord.create(
            account=account_id,
            target_id=target_id,
            verified=verified
        )
    
    def get_accounts_not_following(self, target_id: str, limit: int = 10):
        """Get active accounts that haven't followed the target."""
        followed_accounts = FollowRecord.select(FollowRecord.account).where(
            FollowRecord.target_id == target_id
        )
        now = datetime.datetime.now()
        return list(Account.select()
            .where(Account.status == 'active')
            .where((Account.cooldown_until.is_null()) | (Account.cooldown_until < now))
            .where(Account.id.not_in(followed_accounts))
            .limit(limit))

    # ===== Proxy Methods =====
    
    def add_proxy(self, server: str, username: str = None, password: str = None, source: str = None):
        """Add or update a proxy."""
        try:
            proxy, created = Proxy.get_or_create(
                server=server,
                defaults={
                    'username': username,
                    'password': password,
                    'source': source
                }
            )
            if not created:
                proxy.username = username
                proxy.password = password
                proxy.save()
            return proxy
        except IntegrityError:
            return None
    
    def update_proxy_health(self, server: str, is_working: bool, latency_ms: int = None):
        """Update proxy health status."""
        try:
            proxy = Proxy.get(Proxy.server == server)
            proxy.is_working = is_working
            proxy.last_checked = datetime.datetime.now()
            if latency_ms:
                proxy.latency_ms = latency_ms
            if is_working:
                proxy.success_count += 1
            else:
                proxy.fail_count += 1
            proxy.save()
        except Proxy.DoesNotExist:
            # Create new proxy record
            Proxy.create(
                server=server,
                is_working=is_working,
                latency_ms=latency_ms,
                success_count=1 if is_working else 0,
                fail_count=0 if is_working else 1
            )
    
    def get_working_proxies(self, limit: int = 50):
        """Get working proxies sorted by success rate."""
        return list(Proxy.select()
                   .where(Proxy.is_working == True)
                   .order_by(Proxy.latency_ms.asc())
                   .limit(limit))
    
    def get_proxy_stats(self):
        """Get proxy pool statistics."""
        total = Proxy.select().count()
        working = Proxy.select().where(Proxy.is_working == True).count()
        avg_latency = Proxy.select(fn.AVG(Proxy.latency_ms)).where(Proxy.is_working == True).scalar()
        return {
            'total': total,
            'working': working,
            'failed': total - working,
            'avg_latency_ms': round(avg_latency) if avg_latency else None
        }

    # ===== Account Methods =====
    
    def save_account(self, data: dict):
        """Save a new account."""
        return Account.create(**data)
    
    def get_account(self, username: str):
        """Get account by username."""
        try:
            return Account.get(Account.username == username)
        except Account.DoesNotExist:
            return None
    
    def get_active_account(self):
        """Get a random active account that's not on cooldown."""
        now = datetime.datetime.now()
        return (Account.select()
                .where(Account.status == 'active')
                .where((Account.cooldown_until.is_null()) | (Account.cooldown_until < now))
                .order_by(fn.Random())
                .first())
    
    def get_account_by_least_used(self):
        """Get the active account with lowest usage."""
        now = datetime.datetime.now()
        return (Account.select()
                .where(Account.status == 'active')
                .where((Account.cooldown_until.is_null()) | (Account.cooldown_until < now))
                .order_by(Account.follow_count.asc())
                .first())
    
    def set_account_cooldown(self, account_id: int, minutes: int = 30):
        """Set cooldown for an account."""
        account = Account.get_by_id(account_id)
        account.cooldown_until = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
        account.last_used = datetime.datetime.now()
        account.save()
    
    def update_account_status(self, account_id: int, status: str, notes: str = None):
        """Update account status."""
        account = Account.get_by_id(account_id)
        account.status = status
        if notes:
            account.notes = notes
        account.save()
    
    def increment_follow_count(self, account_id: int):
        """Increment the follow count for an account."""
        account = Account.get_by_id(account_id)
        account.follow_count += 1
        account.last_used = datetime.datetime.now()
        account.save()
    
    def get_account_stats(self):
        """Get account statistics."""
        total = Account.select().count()
        active = Account.select().where(Account.status == 'active').count()
        banned = Account.select().where(Account.status == 'banned').count()
        total_follows = Account.select(fn.SUM(Account.follow_count)).scalar() or 0
        return {
            'total': total,
            'active': active,
            'banned': banned,
            'other': total - active - banned,
            'total_follows': total_follows
        }
    
    def get_all_accounts(self, limit: int = 100):
        """Get all accounts."""
        return list(Account.select().order_by(Account.created_at.desc()).limit(limit))
    
    def count_accounts(self):
        """Get total account count."""
        return Account.select().count()

    # ===== Task Log Methods =====
    
    def log_task(self, task_type: str, status: str, target: str = None, 
                 account_id: int = None, error_message: str = None, 
                 duration_seconds: float = None, proxy_used: str = None):
        """Log a task execution."""
        return TaskLog.create(
            task_type=task_type,
            status=status,
            target=target,
            account=account_id,
            error_message=error_message,
            duration_seconds=duration_seconds,
            proxy_used=proxy_used
        )
    
    def get_task_stats(self, hours: int = 24):
        """Get task statistics for the last N hours."""
        since = datetime.datetime.now() - datetime.timedelta(hours=hours)
        
        total = TaskLog.select().where(TaskLog.timestamp > since).count()
        success = TaskLog.select().where(
            (TaskLog.timestamp > since) & 
            (TaskLog.status == 'success')
        ).count()
        
        by_type = {}
        for log in (TaskLog.select(TaskLog.task_type, fn.COUNT(TaskLog.id).alias('count'))
                   .where(TaskLog.timestamp > since)
                   .group_by(TaskLog.task_type)):
            by_type[log.task_type] = log.count
        
        return {
            'total': total,
            'success': success,
            'failed': total - success,
            'success_rate': round(success / total * 100, 1) if total > 0 else 0,
            'by_type': by_type
        }
    
    def get_recent_errors(self, limit: int = 10):
        """Get recent task errors."""
        return list(TaskLog.select()
                   .where(TaskLog.status != 'success')
                   .where(TaskLog.error_message.is_null(False))
                   .order_by(TaskLog.timestamp.desc())
                   .limit(limit))
