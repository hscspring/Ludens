from __future__ import annotations

import copy
import json
import logging

import requests

from llm_client import LLMClient
from pipeline.tavern.data_model import ObjectLead, SceneReply

LOG = logging.getLogger(__name__)


class InteractionProtocol:
    def validate(self, task: str, context: dict, raw: dict) -> dict | None:
        if task == 'public_leads':
            if set(raw) != {'object_leads'} or not isinstance(raw['object_leads'], dict):
                raise ValueError('Expected an object_leads dictionary')
            if set(raw['object_leads']) != {obj['id'] for obj in context['objects']}:
                raise ValueError('Object lead IDs must match current objects')
            for lead in raw['object_leads'].values():
                parsed = ObjectLead.model_validate(lead, strict=True)
                if len(parsed.options) != 2 or set(lead) - ObjectLead.model_fields.keys():
                    raise ValueError('Each object needs a hint and two options')
            return None
        reply = SceneReply.model_validate(raw, strict=True)
        if set(raw) - SceneReply.model_fields.keys() or not 2 <= len(reply.suggestions) <= 3:
            raise ValueError('Unexpected fields or missing response options')
        world = copy.deepcopy(context['world'])
        objects = {obj['id']: obj for obj in world['objects']}
        ids = set(objects)
        updates = [obj.id for obj in reply.object_updates]
        if len(updates) != len(set(updates)) or set(updates) - ids or set(reply.reactions) - ids:
            raise ValueError('Duplicate or unknown object IDs')
        if reply.attention not in ids | {None, 'character'}:
            raise ValueError('Unknown attention target')
        if reply.moment and reply.moment.target not in ids | {'character'}:
            raise ValueError('Unknown story moment target')
        excerpts = reply.memories + [quote.quote for quote in reply.object_quotes]
        if any(not text.strip() or len(text) > 300 or text not in reply.line for text in excerpts):
            raise ValueError('Memory or quote is not an exact reply excerpt')
        if len(set(reply.memories)) != len(reply.memories) or any(q.target not in ids for q in reply.object_quotes):
            raise ValueError('Duplicate memory or unknown quote target')
        if reply.video_line and reply.video_line not in reply.line:
            raise ValueError('Video speech is not an exact reply excerpt')
        for obj in reply.object_updates:
            objects[obj.id].update(obj.model_dump())
        if reply.appearance is not None:
            world['appearance'] = reply.appearance
        return world


class InteractionModel:
    def __init__(self, fallback: LLMClient, url: str) -> None:
        self.fallback = fallback
        self.protocol = InteractionProtocol()
        self.primary = LLMClient(endpoints=[{
            "name": "ludens-sft-v1", "base_url": url, "model": "ludens-sft-v1",
            "key_env": "LUDENS_SFT_KEY", "timeout": (2, 20),
            "params": {"stream": False, "chat_template_kwargs": {"enable_thinking": False}},
        }]) if url else None

    def __call__(self, task: str, system: str, user: str, **overrides: object) -> dict:
        if self.primary is not None:
            try:
                raw = self.primary.call_json(system, user, **{**overrides, "temperature": 0, "max_tokens": 2048})
                self.protocol.validate(task, json.loads(user), raw)
                LOG.info("SFT accepted interaction task=%s", task)
                return raw
            except (requests.RequestException, KeyError, ValueError, RuntimeError) as error:
                LOG.warning("SFT task=%s failed; using existing model: %s", task, error)
        return self.fallback.call_json(system, user, **overrides)
