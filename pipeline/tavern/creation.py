from __future__ import annotations

import base64
import json
import logging
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from llm_client import ENDPOINTS, LLMClient
from pipeline.tavern.data_model import SceneCreate, ScenePlan
from pipeline.tavern.layout import SceneLayout

if TYPE_CHECKING:
    from pipeline.tavern.api import TavernService

LOG = logging.getLogger(__name__)
ART_STYLE = (
    'Preserve the reference rendering technique: delicate skin detail, continuous soft facial shading, '
    'sculpted facial planes, fine hair strands, rich fabric texture, deep cool shadows and restrained highlights. '
    'Create a beautiful fictional game character with refined semi-realistic features, not a photograph of an actor. '
    'The supplied reference defines surface rendering ONLY. Replace its identity, clothing, pose and location '
    'with the requested character and scene. Preserve the requested age, gender, ethnicity, physique and distinctive features. '
    'Render the person, props and environment coherently, with no flat cel shading, heavy outlines, plastic toy faces or chibi proportions. '
)


class SceneCreator:
    def __init__(self, service: TavernService, root: Path, image_url: str) -> None:
        self.service = service
        self.root = root
        self.image_url = image_url.rstrip('/')
        self.reference = base64.b64encode((Path(__file__).parent / 'cards/style_reference.webp').read_bytes()).decode()
        self.llm = LLMClient(endpoints=[ENDPOINTS[0]])
        self.layout = SceneLayout(self.llm, image_url)
        self.jobs = queue.Queue()
        self.results = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, source: SceneCreate) -> dict:
        if not self.image_url:
            raise ValueError('生图服务尚未连接，暂时不能创建新场景。')
        identifier = uuid.uuid4().hex
        with self.lock:
            self.results[identifier] = {'id': identifier, 'status': 'queued', 'stage': '等待创建', 'started': time.time()}
        self.jobs.put((identifier, source))
        return self.status(identifier)

    def status(self, identifier: str) -> dict:
        with self.lock:
            return dict(self.results[identifier])

    def _stage(self, identifier: str, stage: str) -> None:
        with self.lock:
            self.results[identifier].update(status='working', stage=stage)

    def _work(self) -> None:
        while True:
            identifier, source = self.jobs.get()
            try:
                self._build(identifier, source)
                with self.lock:
                    self.results[identifier].update(status='ready', stage='可以进入了', story_id=identifier)
            except (requests.RequestException, ValueError, RuntimeError, OSError, KeyError, TypeError):
                LOG.exception('Scene creation failed: %s', identifier)
                with self.lock:
                    self.results[identifier].update(status='failed', error='场景生成或画面校验未通过。请重试，或换一个单人、单场景的开场。')
            finally:
                self.jobs.task_done()

    @staticmethod
    def plan(llm: LLMClient, source: SceneCreate) -> tuple[ScenePlan, dict]:
        raw = llm.call_json(
            'Compile the supplied roleplay card into ONE playable opening. Preserve the original identity, gender, relationships and history. '
            'The user is an important participant, not an outside adviser. welcomeMessage may contain extensive events that have ALREADY happened. '
            'Preserve names exactly as written, without inventing translated names. Never assign a player gender absent from the source; use neutral relationship terms. '
            'Do not reveal private personality facts to the player in prologue; respect uncertainty and rumors in welcomeMessage. '
            'An opening emotion is not permanent: do not turn trauma, reluctance or hostility into an unchangeable rule. '
            'Start at its final moment. Never decide the next player action or impose a resolution. '
            'Supported visual scope: one primary visible NPC in one stable location, user is the unseen viewpoint. '
            'If essential facts cannot fit this scope, supported=false and explain why. Do not silently change the story. '
            'Select 1-4 actual visible objects, including environmental features or accessories if appropriate. '
            'Use only objects justified by the card or ordinary necessary furnishings; no arbitrary puzzle props, extra characters or invented emergencies. '
            'For objects with explicit readable content in the source, copy that public content faithfully into contents; otherwise contents is empty. '
            'Do not include hidden truth, deductions or private thoughts in contents. Never require generated image text to be legible. '
            'Write a detailed English image_prompt for a coherent wide 7:4 illustration of the CURRENT scene, one NPC, natural proportions, '
            'clearly visible face, calm stationary pose, hands at rest, visible requested props, no text or UI. '
            + ART_STYLE +
            'All other prose Chinese. Return JSON matching this schema: ' + json.dumps(ScenePlan.model_json_schema(), ensure_ascii=False),
            source.model_dump_json(), temperature=.5, max_tokens=3500,
        )
        plan = ScenePlan.model_validate(raw)
        if not plan.supported:
            return plan, {"valid": False, "issues": [plan.reason]}
        ids = [obj.id for obj in plan.objects]
        if len(ids) != len(set(ids)) or 'character' in ids:
            raise ValueError('Object IDs must be unique and distinct from character')
        audit = llm.call_json(
            'Audit an adaptation of a roleplay card. Return JSON {valid:boolean,issues:[string]}. '
            'Reject invented player gender, changed names, changed role/relationships, exposing private facts not available to the player, '
            'invented prior events, permanent constraints not in source, or choosing the player next response. '
            'Allow reasonable visual furnishings and translation of prose, but retain names as written in source. '
            'Check whether the image prompt describes exactly ONE visible NPC and the correct final location. Be precise.',
            json.dumps({'source':source.model_dump(),'plan':plan.model_dump()}, ensure_ascii=False), temperature=0, max_tokens=900,
        )
        return plan, audit

    def _build(self, identifier: str, source: SceneCreate) -> None:
        folder = self.root / 'media' / 'created' / identifier
        folder.mkdir(parents=True)
        self._stage(identifier, '理解角色、你的身份与开场')
        plan, audit = self.plan(self.llm, source)
        ids = [obj.id for obj in plan.objects]
        (folder / 'plan_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
        if not audit['valid']:
            raise ValueError('Opening adaptation changed source facts: ' + '; '.join(audit['issues']))
        (folder / 'plan.json').write_text(plan.model_dump_json(indent=2))
        for attempt in range(2):
            self._stage(identifier, '生成场景画面' if attempt == 0 else '画面未通过校验，重新生成')
            instruction = ART_STYLE + 'Create a NEW wide 7:4 scene, with full head and the requested props visible. '
            instruction += plan.image_prompt + ' Exactly ONE visible person. The viewer is not shown. No split panels, captions or UI. '
            if attempt:
                instruction += 'Correct the preceding failed visual check in this new composition: ' + json.dumps(grounded, ensure_ascii=False)
            frame = self.layout.image('/edit', {'image':self.reference, 'instruction':instruction})
            self._stage(identifier, '识别画面中的人物与物品')
            grounded = self.layout.locate(frame, [obj.model_dump() for obj in plan.objects], plan.image_prompt)
            frame.save(folder / 'candidate.webp', lossless=True)
            (folder / 'grounding.json').write_text(json.dumps(grounded, ensure_ascii=False, indent=2))
            found = grounded['objects']
            if (grounded['character_matches'] and grounded['visible_people_count'] == 1 and grounded['scene_matches'] and grounded['objects_belong_to_same_character']
                    and grounded['character']['visible'] and sorted(obj['id'] for obj in found) == sorted(ids)
                    and all(obj['visible'] for obj in found)):
                break
        else:
            raise ValueError('Scene, character count or requested objects failed visual validation')
        assets = self.layout.build(frame, grounded, folder)
        self._stage(identifier, '校验并保存可玩场景')
        card = {**source.model_dump(), 'id':identifier, 'character':plan.character, 'entry':plan.entry,
                'object_contents':{obj.id:obj.contents for obj in plan.objects if obj.contents},
                'visible_objects':{obj['id']:obj['description'] for obj in found},
                'capabilities':'交流、等待、查看已知物品；movable=true的物品可直接小幅平移。可通过对话提出拿取、放置、收起或戴回已有便携物品的意图，由角色回应确认状态变化。不可换场景或凭空新增物品。',
                'presentation':{'title':plan.title, 'character':plan.character, 'intro':plan.player_role,
                                'prologue':plan.prologue, 'opening_line':plan.opening_line,
                                'placeholder':'你想怎样回应？', 'rest':'接下来怎样回应，由你决定。'}}
        config = {'assets':assets, 'video':dict(self.service.video.config)}
        config['video'].update(voice='a natural voice matching the character', ambience='quiet ambience matching the scene')
        output = self.root / 'created'
        output.mkdir(exist_ok=True)
        path = output / f'{identifier}.json'
        path.write_text(json.dumps({'validated':True,'card':card,'config':config}, ensure_ascii=False, indent=2))
        self.service.register(card, config)
