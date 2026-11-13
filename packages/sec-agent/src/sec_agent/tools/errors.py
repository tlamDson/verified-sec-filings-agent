"""Why a tool refused a request. A value that is simply not reported is a result, not an error."""

from typing import ClassVar


class ToolError(Exception):
    """Base class. `code` is a stable name the agent and the MCP server can switch on."""

    code: ClassVar[str] = "tool_error"


class UnknownCompanyError(ToolError):
    """The company is outside the product's universe (E7), or unknown."""

    code = "unknown_company"


class AmbiguousCompanyError(ToolError):
    """A name matches more than one company; ask with the ticker."""

    code = "ambiguous_company"


class UnknownMetricError(ToolError):
    """No canonical concept or ratio by that name (non-GAAP measures are not in XBRL, E4)."""

    code = "unknown_metric"


class InvalidRequestError(ToolError):
    """The arguments are valid one by one but do not make one question together."""

    code = "invalid_request"


class AmbiguousFactError(ToolError):
    """More than one period carries the same fiscal label: the data, not the question, is wrong."""

    code = "ambiguous_fact"
