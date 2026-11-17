import json
import uuid
from django import template
register=template.Library()

@register.simple_tag
def operation_uuid(): return str(uuid.uuid4())

@register.filter
def as_json(value): return json.dumps(value,ensure_ascii=False,indent=2)
