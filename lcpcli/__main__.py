"""
What to do if the module is called like this: python -m lcpcli
"""

from .cli import _parse_cmd_line
from .lcpcli import Lcpcli

Lcpcli(**_parse_cmd_line())
