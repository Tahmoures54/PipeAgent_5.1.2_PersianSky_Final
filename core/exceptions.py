# -*- coding: utf-8 -*-
"""
core/exceptions.py – PipeAgent
===============================
Custom exception hierarchy with error codes, context tracking,
and serialization support.

Hierarchy (نمای درختی):
    PipeAgentError
    ├── AppError                    (خطاهای عمومی برنامه)
    ├── ConfigurationError          (تنظیمات و پیکربندی)
    ├── ValidationError             (اعتبارسنجی ورودی‌ها)
    ├── NotFoundError               (موجودیت یافت نشد)
    ├── ConflictError               (تداخل / رکورد تکراری)
    ├── DomainError                 (نقض قوانین کسب‌وکار)
    ├── DatabaseError               (پایگاه داده)
    ├── CacheError                  (کش / حافظه موقت)
    ├── AuthenticationError         (احراز هویت)
    ├── AuthorizationError          (مجوز دسترسی)
    ├── LicenseError                (لایسنس)
    ├── NetworkError                (شبکه و ارتباطات)
    │   ├── ConnectionError_
    │   └── TimeoutError_
    ├── IntegrationError            (تبادل داده با سیستم خارجی)
    │   ├── ExternalServiceError
    │   ├── SyncError
    │   ├── ExportError
    │   └── ImportError_
    ├── PipelineError               (خط لوله)
    │   ├── PipelineConfigError
    │   ├── PipelineExecutionError
    │   └── PipelineTimeoutError
    ├── AgentError                  (ایجنت‌ها)
    │   ├── AgentInitError
    │   ├── AgentExecutionError
    │   └── AgentTimeoutError
    ├── PluginError                 (پلاگین / افزونه)
    ├── QueueError                  (صف و تسک)
    ├── ResourceError               (منابع سیستم)
    └── SerializationError          (سریال‌سازی)
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Dict, Optional


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
class ErrorCode(IntEnum):
    """
    کدهای عددی خطا برای لاگ ساختاریافته و پاسخ API.
    هر ماژول بازه‌ی مخصوص خود را دارد.
    """
    # Implementation note.
    UNKNOWN                 = 1000
    GENERAL                 = 1001
    NOT_IMPLEMENTED         = 1002

    # Implementation note.
    CONFIG_MISSING          = 2001
    CONFIG_INVALID          = 2002
    CONFIG_PARSE            = 2003

    # Implementation note.
    VALIDATION_FAILED       = 3001
    SCHEMA_MISMATCH         = 3002
    BUSINESS_RULE_VIOLATION = 3003
    OPERATION_NOT_ALLOWED   = 3004
    STATE_TRANSITION        = 3005
    PRECONDITION_FAILED     = 3006

    # Implementation note.
    ENTITY_NOT_FOUND        = 3501
    DUPLICATE_ENTITY        = 3502
    CONFLICT                = 3503

    # Implementation note.
    DB_CONNECTION           = 4001
    DB_QUERY                = 4002
    DB_INTEGRITY            = 4003
    DB_MIGRATION            = 4004
    DB_TRANSACTION          = 4005

    # Implementation note.
    CACHE_CONNECTION        = 4501
    CACHE_MISS              = 4502
    CACHE_SERIALIZE         = 4503

    # Implementation note.
    AUTH_INVALID_CREDENTIALS = 5001
    AUTH_TOKEN_EXPIRED      = 5002
    AUTH_TOKEN_INVALID      = 5003
    AUTH_SESSION_EXPIRED    = 5004
    AUTH_PERMISSION_DENIED  = 5101
    AUTH_ROLE_MISSING       = 5102

    # Implementation note.
    LICENSE_EXPIRED         = 5501
    LICENSE_INVALID         = 5502
    LICENSE_ACTIVATION      = 5503
    LICENSE_QUOTA_EXCEEDED  = 5504
    LICENSE_TAMPERED        = 5505

    # Implementation note.
    NET_CONNECTION          = 6001
    NET_TIMEOUT             = 6002
    NET_DNS                 = 6003
    NET_SSL                 = 6004

    # Implementation note.
    PIPE_CONFIG             = 7001
    PIPE_EXECUTION          = 7002
    PIPE_TIMEOUT            = 7003
    PIPE_STAGE_FAILED       = 7004
    PIPE_DATA_LOSS          = 7005

    # Implementation note.
    AGENT_INIT              = 8001
    AGENT_EXECUTION         = 8002
    AGENT_TIMEOUT           = 8003
    AGENT_RESOURCE          = 8004

    # Implementation note.
    PLUGIN_LOAD             = 9001
    PLUGIN_COMPAT           = 9002
    PLUGIN_EXECUTION        = 9003

    # Implementation note.
    QUEUE_FULL              = 10001
    QUEUE_TASK_FAILED       = 10002
    QUEUE_DEADLOCK          = 10003

    # Implementation note.
    RESOURCE_MEMORY         = 11001
    RESOURCE_DISK           = 11002
    RESOURCE_CPU            = 11003
    RESOURCE_FILE_NOT_FOUND = 11004

    # Implementation note.
    SERIALIZE_ENCODE        = 12001
    SERIALIZE_DECODE        = 12002

    # Implementation note.
    INTEGRATION_FAILED      = 13001
    EXTERNAL_SERVICE        = 13002
    SYNC_FAILED             = 13003
    EXPORT_FAILED           = 13004
    IMPORT_FAILED           = 13005


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
class PipeAgentError(Exception):
    """
    استثنای پایه‌ی تمام خطاهای PipeAgent.

    Features:
        - error_code:  کد عددی برای ماشین‌خوانی
        - context:     دیکشنری اطلاعات تکمیلی (برای دیباگ)
        - details:     پیام قابل نمایش به کاربر نهایی
        - http_status: کد وضعیت HTTP معادل (برای API)
        - serializable: تبدیل به dict برای JSON / لاگ
    """

    default_code: ErrorCode = ErrorCode.UNKNOWN
    default_message: str = "An unexpected PipeAgent error occurred."
    http_status: int = 500

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[ErrorCode | int] = None,
        context: Optional[Dict[str, Any]] = None,
        details: Optional[str] = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.context: Dict[str, Any] = context or {}
        self.details = details  # Implementation note.

        super().__init__(self.message)

    # Implementation note.
    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.context:
            ctx_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            parts.append(f"  context: {{{ctx_str}}}")
        return "\n".join(parts)

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        return (
            f"{cls}(message={self.message!r}, "
            f"code={self.code!r}, "
            f"context={self.context!r})"
        )

    # Implementation note.
    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری (مناسب JSON / لاگ ساختاریافته)."""
        result: Dict[str, Any] = {
            "error": self.__class__.__name__,
            "code": int(self.code),
            "message": self.message,
            "http_status": self.http_status,
        }
        if self.details:
            result["details"] = self.details
        if self.context:
            result["context"] = self.context
        if self.__cause__:
            result["cause"] = str(self.__cause__)
        return result


# Implementation note.
PipeAgentException = PipeAgentError
BaseError = PipeAgentError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class AppError(PipeAgentError):
    """خطای عمومی برنامه (سازگار با ماژول‌های قدیمی)."""
    default_code = ErrorCode.GENERAL
    default_message = "A general application error occurred."
    http_status = 500


class NotImplementedError_(PipeAgentError):
    """تابع یا قابلیت هنوز پیاده‌سازی نشده."""
    default_code = ErrorCode.NOT_IMPLEMENTED
    default_message = "This feature is not yet implemented."
    http_status = 501


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class ConfigurationError(PipeAgentError):
    """خطا در خواندن یا تفسیر فایل/متغیر پیکربندی."""
    default_code = ErrorCode.CONFIG_INVALID
    default_message = "Invalid configuration."
    http_status = 500


class ConfigMissingError(ConfigurationError):
    """کلید یا فایل پیکربندی یافت نشد."""
    default_code = ErrorCode.CONFIG_MISSING
    default_message = "Required configuration key is missing."


class ConfigParseError(ConfigurationError):
    """خطا در تجزیه (parse) فایل پیکربندی."""
    default_code = ErrorCode.CONFIG_PARSE
    default_message = "Failed to parse configuration file."


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class ValidationError(PipeAgentError):
    """ورودی با schema یا قوانین اعتبارسنجی مطابقت ندارد."""
    default_code = ErrorCode.VALIDATION_FAILED
    default_message = "Validation failed."
    http_status = 400

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        if field:
            self.context["field"] = field
        if value is not None:
            self.context["value"] = value


class SchemaMismatchError(ValidationError):
    """ساختار داده با schema مورد انتظار هم‌خوان نیست."""
    default_code = ErrorCode.SCHEMA_MISMATCH
    default_message = "Data schema mismatch."


# Implementation note.
InvalidDataError = ValidationError
InvalidInputError = ValidationError
SchemaValidationError = SchemaMismatchError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class NotFoundError(PipeAgentError):
    """موجودیت یا رکورد درخواستی در سیستم یافت نشد."""
    default_code = ErrorCode.ENTITY_NOT_FOUND
    default_message = "The requested resource was not found."
    http_status = 404

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        entity: Optional[str] = None,
        entity_id: Optional[Any] = None,
        **kwargs,
    ) -> None:
        if message is None and entity is not None:
            if entity_id is not None:
                message = f"{entity} with id={entity_id!r} was not found."
            else:
                message = f"{entity} was not found."
        super().__init__(message, **kwargs)
        if entity:
            self.context["entity"] = entity
        if entity_id is not None:
            self.context["entity_id"] = entity_id


# Implementation note.
EntityNotFoundError = NotFoundError
RecordNotFoundError = NotFoundError
ResourceNotFoundError = NotFoundError
ObjectNotFoundError = NotFoundError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class ConflictError(PipeAgentError):
    """عملیات با وضعیت فعلی سیستم تداخل دارد."""
    default_code = ErrorCode.CONFLICT
    default_message = "The operation conflicts with the current state."
    http_status = 409


class DuplicateError(ConflictError):
    """رکورد تکراری – موجودیتی با همین کلید یکتا وجود دارد."""
    default_code = ErrorCode.DUPLICATE_ENTITY
    default_message = "A record with the same unique key already exists."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        entity: Optional[str] = None,
        key: Optional[Any] = None,
        **kwargs,
    ) -> None:
        if message is None and entity is not None:
            message = f"{entity} with key={key!r} already exists."
        super().__init__(message, **kwargs)
        if entity:
            self.context["entity"] = entity
        if key is not None:
            self.context["key"] = key


# Implementation note.
DuplicateEntityError = DuplicateError
AlreadyExistsError = DuplicateError
DuplicateRecordError = DuplicateError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class DomainError(PipeAgentError):
    """نقض قوانین منطق تجاری و گردش‌کار سیستم."""
    default_code = ErrorCode.BUSINESS_RULE_VIOLATION
    default_message = "Domain operation could not be completed."
    http_status = 422


class BusinessRuleError(DomainError):
    """قانون کسب‌وکار نقض شده (مثلاً جوشکار فاقد صلاحیت)."""
    default_code = ErrorCode.BUSINESS_RULE_VIOLATION
    default_message = "A business rule was violated."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        rule: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        if rule:
            self.context["rule"] = rule


class OperationNotAllowedError(DomainError):
    """این عملیات در وضعیت فعلی مجاز نیست."""
    default_code = ErrorCode.OPERATION_NOT_ALLOWED
    default_message = "This operation is not allowed in the current state."


class StateTransitionError(DomainError):
    """تغییر وضعیت درخواستی معتبر نیست."""
    default_code = ErrorCode.STATE_TRANSITION
    default_message = "Invalid state transition."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        **kwargs,
    ) -> None:
        if message is None and from_state and to_state:
            message = f"Cannot transition from {from_state!r} to {to_state!r}."
        super().__init__(message, **kwargs)
        if from_state:
            self.context["from_state"] = from_state
        if to_state:
            self.context["to_state"] = to_state


class PreconditionFailedError(DomainError):
    """پیش‌نیازهای لازم برای اجرای عملیات برآورده نشده‌اند."""
    default_code = ErrorCode.PRECONDITION_FAILED
    default_message = "Preconditions for this operation were not met."
    http_status = 412


# Implementation note.
BusinessRuleViolationError = BusinessRuleError
BusinessLogicError = DomainError
WorkflowError = DomainError
RuleViolationError = BusinessRuleError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class DatabaseError(PipeAgentError):
    """خطاهای مرتبط با پایگاه داده."""
    default_code = ErrorCode.DB_QUERY
    default_message = "A database error occurred."
    http_status = 500


class DatabaseConnectionError(DatabaseError):
    """عدم امکان اتصال به پایگاه داده."""
    default_code = ErrorCode.DB_CONNECTION
    default_message = "Cannot connect to the database."


class DatabaseIntegrityError(DatabaseError):
    """نقض قید یکپارچگی (unique, foreign key, ...)."""
    default_code = ErrorCode.DB_INTEGRITY
    default_message = "Database integrity constraint violated."
    http_status = 409


class DatabaseMigrationError(DatabaseError):
    """خطا در اجرای migration."""
    default_code = ErrorCode.DB_MIGRATION
    default_message = "Database migration failed."


class TransactionError(DatabaseError):
    """خطا در commit/rollback تراکنش."""
    default_code = ErrorCode.DB_TRANSACTION
    default_message = "Database transaction failed."


# Implementation note.
RepositoryError = DatabaseError
IntegrityError_ = DatabaseIntegrityError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class CacheError(PipeAgentError):
    """خطاهای مرتبط با سیستم کش."""
    default_code = ErrorCode.CACHE_CONNECTION
    default_message = "A cache error occurred."


class CacheMissError(CacheError):
    """کلید مورد نظر در کش یافت نشد."""
    default_code = ErrorCode.CACHE_MISS
    default_message = "Cache key not found."


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class AuthenticationError(PipeAgentError):
    """خطا در ورود / تأیید هویت."""
    default_code = ErrorCode.AUTH_INVALID_CREDENTIALS
    default_message = "Authentication failed."
    http_status = 401


class TokenExpiredError(AuthenticationError):
    """توکن منقضی شده است."""
    default_code = ErrorCode.AUTH_TOKEN_EXPIRED
    default_message = "Authentication token has expired."


class TokenInvalidError(AuthenticationError):
    """توکن نامعتبر یا دستکاری‌شده."""
    default_code = ErrorCode.AUTH_TOKEN_INVALID
    default_message = "Invalid authentication token."


class SessionExpiredError(AuthenticationError):
    """نشست کاربر منقضی شده است."""
    default_code = ErrorCode.AUTH_SESSION_EXPIRED
    default_message = "User session has expired."


class AuthorizationError(PipeAgentError):
    """کاربر هویت دارد ولی مجوز لازم را ندارد."""
    default_code = ErrorCode.AUTH_PERMISSION_DENIED
    default_message = "Permission denied."
    http_status = 403


class RoleMissingError(AuthorizationError):
    """نقش لازم برای انجام این عملیات به کاربر تخصیص نیافته."""
    default_code = ErrorCode.AUTH_ROLE_MISSING
    default_message = "Required role is missing for this operation."


# Implementation note.
AuthError = AuthenticationError
InvalidCredentialsError = AuthenticationError
PermissionDeniedError = AuthorizationError
ForbiddenError = AuthorizationError
AccessDeniedError = AuthorizationError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class LicenseError(PipeAgentError):
    """خطاهای اعتبارسنجی / فعال‌سازی لایسنس."""
    default_code = ErrorCode.LICENSE_INVALID
    default_message = "License validation failed."
    http_status = 403


class LicenseExpiredError(LicenseError):
    """تاریخ انقضای لایسنس گذشته است."""
    default_code = ErrorCode.LICENSE_EXPIRED
    default_message = "License has expired."


class LicenseInvalidError(LicenseError):
    """لایسنس نامعتبر است."""
    default_code = ErrorCode.LICENSE_INVALID
    default_message = "License is invalid."


class LicenseActivationError(LicenseError):
    """فعال‌سازی لایسنس با شکست مواجه شد."""
    default_code = ErrorCode.LICENSE_ACTIVATION
    default_message = "License activation failed."


class LicenseQuotaExceededError(LicenseError):
    """سقف مجاز لایسنس (تعداد کاربر، API call و...) رد شده."""
    default_code = ErrorCode.LICENSE_QUOTA_EXCEEDED
    default_message = "License quota exceeded."


class LicenseTamperedError(LicenseError):
    """فایل لایسنس دستکاری شده است."""
    default_code = ErrorCode.LICENSE_TAMPERED
    default_message = "License file appears to be tampered with."


# Implementation note.
LicenseLimitExceededError = LicenseQuotaExceededError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class NetworkError(PipeAgentError):
    """خطاهای ارتباط شبکه‌ای."""
    default_code = ErrorCode.NET_CONNECTION
    default_message = "A network error occurred."
    http_status = 503


class ConnectionError_(NetworkError):
    """عدم امکان برقراری اتصال."""
    default_code = ErrorCode.NET_CONNECTION
    default_message = "Failed to establish connection."


class TimeoutError_(NetworkError):
    """اتصال یا درخواست در زمان مقرر پاسخ نداد."""
    default_code = ErrorCode.NET_TIMEOUT
    default_message = "Operation timed out."
    http_status = 504


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class IntegrationError(PipeAgentError):
    """خطا در تبادل داده با سیستم‌های خارجی (ERP, BIM, DMS)."""
    default_code = ErrorCode.INTEGRATION_FAILED
    default_message = "An error occurred during external integration."
    http_status = 502


class ExternalServiceError(IntegrationError):
    """سرویس خارجی پاسخ نامعتبر یا خطا برگرداند."""
    default_code = ErrorCode.EXTERNAL_SERVICE
    default_message = "External service returned an error."


class SyncError(IntegrationError):
    """خطا در همگام‌سازی داده‌ها."""
    default_code = ErrorCode.SYNC_FAILED
    default_message = "Data synchronization failed."


class ExportError(IntegrationError):
    """خطا در خروجی‌گیری (Excel, PDF, HTML)."""
    default_code = ErrorCode.EXPORT_FAILED
    default_message = "Data export failed."


class ImportError_(IntegrationError):
    """خطا در ورود داده (Import)."""
    default_code = ErrorCode.IMPORT_FAILED
    default_message = "Data import failed."


# Implementation note.
DataExchangeError = IntegrationError


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class PipelineError(PipeAgentError):
    """خطاهای مربوط به تعریف یا اجرای پایپ‌لاین."""
    default_code = ErrorCode.PIPE_EXECUTION
    default_message = "Pipeline error."


class PipelineConfigError(PipelineError):
    """پیکربندی پایپ‌لاین ناقص یا نادرست است."""
    default_code = ErrorCode.PIPE_CONFIG
    default_message = "Invalid pipeline configuration."


class PipelineExecutionError(PipelineError):
    """خطا هنگام اجرای یکی از stageهای پایپ‌لاین."""
    default_code = ErrorCode.PIPE_EXECUTION
    default_message = "Pipeline execution failed."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        stage: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        if stage:
            self.context["stage"] = stage


class PipelineTimeoutError(PipelineError):
    """اجرای پایپ‌لاین بیش از حد مجاز طول کشید."""
    default_code = ErrorCode.PIPE_TIMEOUT
    default_message = "Pipeline execution timed out."


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class AgentError(PipeAgentError):
    """خطاهای مربوط به ایجنت‌ها."""
    default_code = ErrorCode.AGENT_EXECUTION
    default_message = "Agent error."


class AgentInitError(AgentError):
    """ایجنت در مرحله‌ی مقداردهی اولیه شکست خورد."""
    default_code = ErrorCode.AGENT_INIT
    default_message = "Agent initialization failed."


class AgentExecutionError(AgentError):
    """خطا در حین اجرای ایجنت."""
    default_code = ErrorCode.AGENT_EXECUTION
    default_message = "Agent execution failed."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        agent_name: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        if agent_name:
            self.context["agent"] = agent_name


class AgentTimeoutError(AgentError):
    """ایجنت در زمان مقرر پاسخ نداد."""
    default_code = ErrorCode.AGENT_TIMEOUT
    default_message = "Agent execution timed out."


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class PluginError(PipeAgentError):
    """خطاهای بارگذاری یا اجرای پلاگین."""
    default_code = ErrorCode.PLUGIN_LOAD
    default_message = "Plugin error."


class PluginCompatibilityError(PluginError):
    """پلاگین با نسخه‌ی فعلی PipeAgent سازگار نیست."""
    default_code = ErrorCode.PLUGIN_COMPAT
    default_message = "Plugin is not compatible with this PipeAgent version."


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class QueueError(PipeAgentError):
    """خطاهای صف پیام / تسک."""
    default_code = ErrorCode.QUEUE_TASK_FAILED
    default_message = "Queue error."


class QueueFullError(QueueError):
    """صف پر شده و تسک جدید قابل پذیرش نیست."""
    default_code = ErrorCode.QUEUE_FULL
    default_message = "Queue is full."


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class ResourceError(PipeAgentError):
    """کمبود یا عدم دسترسی به منابع سیستم."""
    default_code = ErrorCode.RESOURCE_MEMORY
    default_message = "System resource error."


class FileNotFoundResourceError(ResourceError):
    """فایل یا مسیر مورد نظر وجود ندارد."""
    default_code = ErrorCode.RESOURCE_FILE_NOT_FOUND
    default_message = "Required file or path not found."
    http_status = 404


# ══════════════════════════════════════════════
# Implementation note.
# ══════════════════════════════════════════════
class SerializationError(PipeAgentError):
    """خطا در encode/decode داده."""
    default_code = ErrorCode.SERIALIZE_ENCODE
    default_message = "Serialization error."


class DeserializationError(SerializationError):
    """خطا در decode داده."""
    default_code = ErrorCode.SERIALIZE_DECODE
    default_message = "Deserialization error."


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────
def raise_from(
    exc_class: type[PipeAgentError],
    original: BaseException,
    *,
    message: Optional[str] = None,
    **kwargs,
) -> None:
    """
    یک استثنای PipeAgent را با حفظ زنجیره‌ی علت (cause) بالا ببرد.

    Example:
        try:
            db.connect()
        except psycopg2.OperationalError as e:
            raise_from(DatabaseConnectionError, e, message="DB unreachable")
    """
    raise exc_class(message, **kwargs) from original


def to_http_response(exc: BaseException) -> Dict[str, Any]:
    """
    تبدیل هر استثنا به ساختار پاسخ استاندارد API.
    برای استفاده در api_server.py / exception handlerها.
    """
    if isinstance(exc, PipeAgentError):
        return exc.to_dict()
    return {
        "error": exc.__class__.__name__,
        "code": int(ErrorCode.UNKNOWN),
        "message": str(exc),
        "http_status": 500,
    }


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────
__all__ = [
    # Enum & Base
    "ErrorCode",
    "PipeAgentError", "PipeAgentException", "BaseError",
    # General
    "AppError", "NotImplementedError_",
    # Config
    "ConfigurationError", "ConfigMissingError", "ConfigParseError",
    # Validation
    "ValidationError", "SchemaMismatchError",
    "InvalidDataError", "InvalidInputError", "SchemaValidationError",
    # Not Found
    "NotFoundError", "EntityNotFoundError", "RecordNotFoundError",
    "ResourceNotFoundError", "ObjectNotFoundError",
    # Conflict / Duplicate
    "ConflictError", "DuplicateError", "DuplicateEntityError",
    "AlreadyExistsError", "DuplicateRecordError",
    # Domain / Business
    "DomainError", "BusinessRuleError", "OperationNotAllowedError",
    "StateTransitionError", "PreconditionFailedError",
    "BusinessRuleViolationError", "BusinessLogicError",
    "WorkflowError", "RuleViolationError",
    # Database
    "DatabaseError", "DatabaseConnectionError", "DatabaseIntegrityError",
    "DatabaseMigrationError", "TransactionError",
    "RepositoryError", "IntegrityError_",
    # Cache
    "CacheError", "CacheMissError",
    # Auth
    "AuthenticationError", "TokenExpiredError", "TokenInvalidError",
    "SessionExpiredError", "AuthorizationError", "RoleMissingError",
    "AuthError", "InvalidCredentialsError", "PermissionDeniedError",
    "ForbiddenError", "AccessDeniedError",
    # License
    "LicenseError", "LicenseExpiredError", "LicenseInvalidError",
    "LicenseActivationError", "LicenseQuotaExceededError",
    "LicenseTamperedError", "LicenseLimitExceededError",
    # Network
    "NetworkError", "ConnectionError_", "TimeoutError_",
    # Integration
    "IntegrationError", "ExternalServiceError", "SyncError",
    "ExportError", "ImportError_", "DataExchangeError",
    # Pipeline
    "PipelineError", "PipelineConfigError", "PipelineExecutionError",
    "PipelineTimeoutError",
    # Agent
    "AgentError", "AgentInitError", "AgentExecutionError", "AgentTimeoutError",
    # Plugin
    "PluginError", "PluginCompatibilityError",
    # Queue
    "QueueError", "QueueFullError",
    # Resource
    "ResourceError", "FileNotFoundResourceError",
    # Serialization
    "SerializationError", "DeserializationError",
    # Utils
    "raise_from", "to_http_response",
]