"""Pure knowledge request grammar shared by the entry boundary and router."""
from __future__ import annotations

from dataclasses import dataclass
import re

from service.utterance_shape import is_mention, is_prohibition


@dataclass(frozen=True)
class KnowledgeEnvelope:
    tools: tuple[str, ...]
    bindings: dict[str, dict]


def knowledge_envelope(text: str) -> KnowledgeEnvelope | None:
    """Recognize literal knowledge fields before interpreting their contents.

    An addressed malformed request returns an empty envelope for clarification.
    For a valid save/edit header, all bytes after its newline belong to the body.
    No tool, source, configuration, model or persisted state is accessed here.
    """
    surface = r"(?:knowledge(?:\s+notes?)?|style\s+examples?|follow-up\s+candidates?)"
    if not re.search(r"\b" + surface + r"\b", text, re.I):
        return None
    why = is_prohibition(text) or is_mention(text)
    value = text.strip()
    prefix = r"(?:please\s+)?"
    labels = {'knowledge note':'knowledge', 'style example':'style_example',
              'follow-up candidate':'followup_candidate'}
    label = r"(?P<kind>knowledge\s+note|style\s+example|follow-up\s+candidate)"
    saved = re.fullmatch(prefix + r"(?:save|store|remember)\s+(?:a\s+)?" + label
        + r"\s+titled\s+(?P<title>[^\r\n]+):\r?\n(?P<body>[\s\S]+)", text.lstrip(), re.I)
    imported = re.fullmatch(prefix + r"(?:save|store)\s+(?P<source>email|messages)\s+"
        r"(?P<id>[^\s]+)\s+in\s+(?P<container_label>account|chat)\s+(?P<container>[^\s]+)"
        r"\s+as\s+(?:a\s+)?" + label + r"\s+titled\s+(?P<title>[^\r\n]+)", value, re.I)
    read = re.fullmatch(prefix + r"(?:read|show|list)\s+(?:my\s+)?(?:saved\s+)?"
        + r'(?P<kind>' + surface + r")(?:\s+(?P<id>(?-i:[0-9a-f]{32})))?[.!?]?", value, re.I)
    edit = re.fullmatch(prefix + r"(?:update|edit|replace)\s+knowledge\s+"
        r"(?P<id>(?-i:[0-9a-f]{32}))\s+titled\s+(?P<title>[^\r\n]+):\r?\n(?P<body>[\s\S]+)", text.lstrip(), re.I)
    delete = re.fullmatch(prefix + r"(?:delete|remove|forget)\s+knowledge\s+"
        r"(?P<id>(?-i:[0-9a-f]{32}))\.?", value, re.I)
    tools: list[str] = []
    bindings: dict[str, dict] = {}
    if not why and saved:
        tools = ['save_knowledge']
        bindings = {'save_knowledge':{'title':saved['title'], 'text':saved['body'],
                    'kind':labels[re.sub(r'\s+', ' ', saved['kind'].lower())],
                    'source_type':'user_request', 'source_id':'', 'container_id':''}}
    elif not why and imported and imported['container_label'].lower() == (
            'account' if imported['source'].lower() == 'email' else 'chat'):
        tools = ['save_knowledge']
        bindings = {'save_knowledge':{'title':imported['title'], 'text':'',
            'kind':labels[re.sub(r'\s+', ' ', imported['kind'].lower())],
            'source_type':imported['source'].lower(), 'source_id':imported['id'],
            'container_id':imported['container']}}
    elif not why and read:
        tools = ['read_knowledge']
        kind = ('style_example' if read['kind'].lower().startswith('style') else
                'followup_candidate' if read['kind'].lower().startswith('follow-up') else
                '' if read['kind'].lower() == 'knowledge' else 'knowledge')
        bindings = {'read_knowledge':{'record_id':read['id'] or '', 'kind':kind}}
    elif not why and (edit or delete):
        match = edit or delete
        effect = 'edit_knowledge' if edit else 'delete_knowledge'
        tools = ['read_knowledge', effect]
        bindings = {'read_knowledge':{'record_id':match['id']}, effect:{'record_id':match['id']}}
        if edit:
            bindings[effect].update(title=edit['title'], text=edit['body'])
    else:
        # Only claim explicitly addressed incomplete instructions or utterance
        # shapes. Other knowledge questions retain ordinary interpretation.
        addressed = re.match(prefix + r"(?:save|store|remember|read|show|list|"
            r"update|edit|replace|delete|remove|forget)\s+(?:my\s+)?(?:saved\s+)?(?:a\s+)?"
            + surface + r"\b", value, re.I)
        if not why and not addressed:
            return None
    return KnowledgeEnvelope(tuple(tools), bindings)
