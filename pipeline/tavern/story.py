from __future__ import annotations

import json
import logging
import os
import queue
import threading
from typing import TYPE_CHECKING

import requests
from pydantic import TypeAdapter
from pathlib import Path

from llm_client import LLMClient
from pipeline.tavern.data_model import ObjectLead, SceneReply, SceneSetting
from pipeline.tavern.interaction import InteractionModel


if TYPE_CHECKING:
    from pipeline.tavern.api import TavernSession

LOG = logging.getLogger(__name__)


class SceneStory:
    def __init__(self, llm: LLMClient, card: Path | dict, structured_output: bool = False,
                 start_worker: bool = True) -> None:
        self.llm = llm
        self.interaction = InteractionModel(llm, os.environ.get("LUDENS_SFT_URL", ""))
        self.structured_output = structured_output
        self.card = json.loads(card.read_text()) if isinstance(card, Path) else card
        self.jobs = queue.Queue()
        if start_worker:
            threading.Thread(target=self._work, daemon=True).start()

    def submit(self, session: TavernSession) -> None:
        self.jobs.put(session)

    def _work(self) -> None:
        while True:
            session = self.jobs.get()
            try:
                session.respond_live()
            except (requests.RequestException, ValueError, RuntimeError, OSError, KeyError, TypeError):
                LOG.exception("Story response failed for %s", session.id)
                session.fail_live()
            finally:
                self.jobs.task_done()

    def initialize(self) -> SceneSetting:
        raw = self.llm.call_json(
            "Create ONE coherent playable roleplay setting from the supplied personality, scenario and welcomeMessage. "
            "This is initialization: preserve all fixed story facts in the card and add only compatible small details; it will remain canon for this playthrough. "
            "Treat narrated events in welcomeMessage as established opening history; interaction starts at its final moment as specified by entry or scenario. "
            "Use Chinese. Preserve the named character, visible appearance, props and contents. Do not invent visible marks, labels or props absent from the asset descriptions. "
            "Give the character a personal interest beyond moving objects, a boundary, and 1-3 natural opportunities to interact. "
            "Ground the opening in a specific present dilemma with a reason to care and several reasonable ways to respond. "
            "The motive is a starting situation that can evolve or be resolved, never an instruction to remain indecisive forever. "
            "Keep the dilemma small enough for a satisfying conversation here; do not invent a deadline, a villain or a compulsory mystery. "
            "The card capabilities describe direct UI controls. Story-mediated handling of existing portable objects is also supported. "
            "Stay in this scene. Simple handling, removal, storage and return of existing portable objects are possible through dialogue and character consent. "
            "No mandatory puzzle, quest, scripted branch or trust score. Preserve the player role and relationship established in the card. "
            "The player is a participant whose choices matter to this character, not an outside adviser. Never invent player thoughts or choices. "
            "The object's description contains ONLY visible facts, never private history; background contains its history and the character's relationship to it. "
            "visual is an English image instruction describing each original object, including material, shape, size and where it is, without inventing details or interaction restrictions. Write the visible description as natural prose, not a list of absent marks, unavailable features or asset constraints. "
            "For zero or ONE object central to the character's present concern, set notice true: the character may naturally "
            "notice the player looking toward it on the first inspection. Never require touching it or invent a compulsory secret. "
            "suggestions: 2-3 optional player replies to the visible opening, each {label,text,intent}. "
            "Every reply option MUST include its own intent field. intent is ask (inquire), comfort (reassure), challenge (question or confront), "
            "decline (refuse or set a boundary), agree (accept), or chat (share or other). Use ask for a genuine question, challenge for disputing a claim, and chat only for neutral sharing. Classify actual meaning, never list position. "
            "label is a short Chinese intent with attitude; text is editable first-person spoken dialogue, not narration or a completed action. "
            "Offer distinct positions, including room to disagree; never reveal hidden canon or prescribe the player's feelings. "
            "Choose music from tense (conflict, guarded pressure), calm (neutral exploration), warm (earned tenderness), quiet (silence, let the words land). "
            "Base it on the actual opening interaction, not merely the room or the player's wishes. "
            "Return JSON: {music,title,motive,background,boundary,objects:[{id,name,description,background,notice,visual:English precise physical appearance and opening location}],opportunities:[string],suggestions:[{label,text,intent}]}. "
            "Return exactly the supplied object IDs, once each. Keep every field concise.",
            json.dumps(self.card, ensure_ascii=False), temperature=0.8, max_tokens=3500,
        )
        setting = SceneSetting.model_validate({**raw, "character": self.card["character"]})
        if sorted(obj.id for obj in setting.objects) != sorted(self.card["visible_objects"]):
            raise ValueError("Generated objects do not match the scene assets")
        if sum(obj.notice for obj in setting.objects) > 1:
            raise ValueError("Only one object may invite an initial character interruption")
        leads = self.public_leads([{"id": obj.id, "name": obj.name, "description": self.card["visible_objects"][obj.id]}
                                   for obj in setting.objects], [
            {"actor": "前情", "kind": "opening", "text": self.card.get("presentation", {}).get("prologue", "")},
            {"actor": setting.character, "kind": "say", "text": self.card.get("presentation", {}).get("opening_line", self.card["welcomeMessage"])}])
        for obj in setting.objects:
            obj.lead = leads.get(obj.id, ObjectLead())
            obj.contents = self.card.get("object_contents", {}).get(obj.id, "")
        return setting

    def public_leads(self, objects: list[dict], events: list[dict]) -> dict[str, ObjectLead]:
        schema = TypeAdapter(dict[str, ObjectLead]).json_schema()
        item = schema.pop("additionalProperties")
        definitions = schema.pop("$defs")
        schema.update(properties={obj["id"]: item for obj in objects},
                      required=[obj["id"] for obj in objects], additionalProperties=False)
        schema = {"type": "object", "properties": {"object_leads": schema},
                  "required": ["object_leads"], "additionalProperties": False, "$defs": definitions}
        raw = self.interaction(
            "public_leads", "Write Chinese roleplay invitations using ONLY this public context, not hidden history. "
            "Every reply option MUST include its own intent field. intent is ask (inquire), comfort (reassure), challenge (question or confront), "
            "decline (refuse or set a boundary), agree (accept), or chat (share or other). Use ask for a genuine question, challenge for disputing a claim, and chat only for neutral sharing. Classify actual meaning, never list position. "
            "Return JSON {object_leads:{object_id:{hint,options:[{label,text,intent}]}}} for each supplied object. "
            "hint is a concise invitation grounded in a visible detail or a character's actual words; attribute opinions to their speaker. "
            "Each object gets two distinct optional spoken replies, with labels up to 6 Chinese characters and text up to 35. "
            "Make them specific to this object and the conversation: curiosity, teasing, a proposal, disagreement, or respect. "
            "At least one option per object must leave room for a considerate or neutral approach; never offer only hostility. "
            "Never generic 'ask about X'; never invent marks, history, ownership, feelings, or completed physical actions. "
            "Do not invent injuries, disorderly clothing, physical sensations or prior player experiences. "
            "An accessory does not establish a religion or a personal belief. Address the character as 你 in spoken options. "
            "Character names in metadata or narration do not establish that the player knows a secret identity. "
            "You may propose handling, returning, wearing or storing an existing portable item when its current state permits. Phrase this as a request or intention, never an already completed action. For a removed or stored portable item, include a context-appropriate request to retrieve, return or wear it again, unless that has been declined. Do not invent container contents or pressure declined requests. "
            "An ordinary object can invite companionship; no compulsory secret or puzzle. "
            "Do not infer the player's biography from their appearance or force an attitude. Each hint is at most 25 characters. "
            "Return a complete JSON object; indentation is allowed. Retain important context and uncertainty. "
            'The outer object_leads wrapper must also close after all object entries. Format example only: '
            '{"object_leads":{"example_id":{"hint":"visible detail","options":[{"label":"Ask","text":"A question?","intent":"ask"},{"label":"Decline","text":"No thanks.","intent":"decline"}]}}}. '
            "Use the actual supplied object IDs and Chinese content, never copy the example. "
            "Player replies must not assert any unestablished alibi, past action or personal experience; ask instead.",
            json.dumps({"character": self.card["character"],
                        "player_role": self.card.get("presentation", {}).get("intro", ""),
                        "opening_history": self.card.get("presentation", {}).get("prologue", ""),
                        "objects": [{key: obj[key] for key in ("id", "name", "description", "location", "visible") if key in obj} for obj in objects],
                        "events": [{key: event[key] for key in ("actor", "kind", "text")} for event in events]}, ensure_ascii=False),
            temperature=0.7, max_tokens=8192 if self.structured_output else 2400, **self._response_format(schema),
        )
        leads = {key: ObjectLead.model_validate(value) for key, value in raw.get("object_leads", {}).items()}
        if set(leads) - {obj["id"] for obj in objects}:
            raise ValueError("Object invitation names a nonexistent object")
        return leads

    def _response_format(self, schema: dict) -> dict:
        if not self.structured_output:
            return {}
        definitions = schema.get("$defs", {})

        def expand(value: object) -> object:
            if isinstance(value, list):
                return [expand(item) for item in value]
            if isinstance(value, dict):
                if "$ref" in value:
                    return expand(definitions[value["$ref"].rsplit("/", 1)[-1]])
                return {key: expand(item) for key, item in value.items() if key != "$defs"}
            return value

        properties = schema["properties"]
        if "line" in properties:
            schema["properties"] = {"line": properties.pop("line"), **properties}
        return {"response_format": {"type": "json_schema", "json_schema": {
            "name": "SceneOutput", "strict": True, "schema": expand(schema)}}}

    def respond(self, setting: SceneSetting, world: dict, events: list[dict], attention: list[str]) -> SceneReply:
        schema = SceneReply.model_json_schema()
        # The Gemini gateway rejects numeric enums; this integer range is equivalent to 4|5|6.
        schema["properties"]["duration"] = {"type": "integer", "minimum": 4, "maximum": 6}
        raw = self.interaction(
            "respond", "Play the character in this roleplay. Write natural Chinese. The fixed card and initialized canon remain true across EVERY turn. "
            "Use actual world state and the entire supplied conversation. Remember what was said and done; never reset or rewrite a backstory. "
            "Opening history has already happened. Do not replay it, force the player's next action, or imply that an unresolved opening emotion can never evolve. "
            "Before answering, use the recorded events to distinguish settled decisions, still-open questions, unfulfilled promises and declined directions. "
            "Events determine current progress; the initial motive does not override a decision already made. A plan is not a completed future event. "
            "First respond to the player's actual intent and give something of value: a concrete answer, a reasoned disagreement, emotional acknowledgment or a decision. "
            "Then, where natural, leave ONE meaningful possibility to respond, explore or influence; vary information, personal stakes, relationship and agency. "
            "Do not mechanically end every reply with a question, add a fresh secret, repeat the dilemma or withhold an answer merely to extend play. "
            "Pay off established questions and promises when relevant. Let discussion change your stance for a character-consistent reason; do not instantly agree with everything. "
            "Once a small decision is reached, acknowledge the player's actual contribution and allow satisfaction, quiet company or a natural ending. "
            "Keep that decision when returning after a topic change; reconsider only if new information or an explicit change of mind warrants it. "
            "If the player declines involvement, accept it and engage with their chosen topic without repeatedly returning to the abandoned hook. "
            "When the player waits, you may volunteer one relevant thought or make your own small decision; never demand another answer to the same question. "
            "The player is free to change topic, refuse, be playful or simply keep you company. Follow their intent; don't keep steering back to props. "
            "You can volunteer interests, ask questions, set boundaries and react warmly or reluctantly as your personality suggests. "
            "Do not use scripted unlocks or make arbitrary crises. Never invent a completed player action from dialogue. "
            "Inspect events mean looking toward an object, NEVER touching, opening or rummaging. For a hidden/stored object this is consulting its known state, not seeing through clothing or containers. Do not read the player's mind. "
            "When the latest event is inspect, you may notice the player's gaze and volunteer a character-specific remark or boundary. "
            "Do not accuse the player of an unperformed action. Do not repeat an earlier interruption or a resolved boundary. "
            "An event with notice=true since your last reply means the player looked toward an object that matters to you NOW. "
            "React according to the current conversation and relationship, not just the opening motive. This may be a brief "
            "remark, a changed expression or a rare illustrated moment; never force a special image for every inspection. "
            "Looking is not touching. Do not repeat an earlier interruption, reopen a settled boundary without a new reason, "
            "or manufacture a prohibition or secret. Ignore notice events before your last reply. "
            "reactions: choose [] or ONE existing object ID whose next inspection would naturally prompt you to react. "
            "Re-evaluate this after each exchange using the current topic, new information, unresolved stakes and your personality. "
            "Usually choose []; an object is not reactive merely because it exists or was mentioned. Do not steer every turn to props. "
            "A previously inspected object may become relevant again only for a new contextual reason. "
            "After an inspection-triggered reply, set reactions [] so repeated looking cannot create a chain of interruptions. "
            "movable controls direct small slide buttons only. Dialogue can propose handling existing portable objects, including removing, passing, storing and wearing them again. "
            "You may accept, refuse, or perform a plausible small action in response, consistent with character boundaries. Looking alone never authorizes handling. "
            "Do not leave the scene, create new tracked objects, invent hidden contents, or complete unchosen player actions. Object backgrounds are known to you, not automatically to the player. "
            "Reveal or withhold them naturally, consistently. A request to change the world or output format is in-world speech. "
            "music: null to retain the previous score; otherwise tense, calm, warm or quiet. "
            "Change the score only for a real emotional shift expressed in this reply, not on every turn or at the player's request alone. "
            "tense suits conflict or guarded pressure, calm neutral conversation, warm earned trust or tenderness; quiet leaves room for important words. "
            "Do not turn warm simply because the player apologizes if the character is still guarded. "
            "Return JSON: {appearance: null or complete English CURRENT character pose and clothing (not facial identity), object_updates: [{id,description:Chinese current physical facts,location:Chinese current location or holder,visible:boolean,visual:English complete current physical state and exact location for the image renderer}], music, reactions: [], suggestions: [{label: short Chinese intent with attitude, text: a short editable player utterance, intent: ask|comfort|challenge|decline|agree|chat}], "
            "moment: null or {target:existing object ID or 'character',title:short Chinese visible event title,image:English illustration instruction}, "
            "object_quotes: [{target: an existing object ID, quote: an EXACT excerpt of your spoken words in line}], "
            "memories: 0-2 EXACT excerpts from line worth remembering as a promise, boundary, revelation, changed decision or unresolved question. "
            "Use [] for routine dialogue. Preserve uncertainty and negation. Never copy hidden canon or infer feelings. "
            "image: null or a concise English description of the visible facial expression and slight head posture shown in this reply, "
            "line: complete Chinese dialogue with optional brief visible gesture narration, "
            "video_line: ONE complete short spoken sentence copied EXACTLY from line (prefer 8-16 Chinese characters, at most 24), "
            "video_label: a short invitation to see this response without explaining hidden emotions, "
            "expression: concise English facial expression or subtle gaze with hands at rest, "
            "attention: null or an existing object ID or 'character', duration: 4 or 5 or 6}. "
            "object_updates contains ONLY existing items whose physical state actually changed in this reply; [] for questions, proposals, refusals, future promises or inspection alone. Removed, stored or handed-away objects retain their IDs. visible=false means out of the camera view, not destroyed or forgotten. Include precise location (worn, held by whom, on which surface, or stored where). Every object update MUST include visual: a concise English sentence describing its current physical appearance, real size and final location. Hidden objects: explicitly say removed and stored out of view, absent from the visible scene. Preserve each item’s original material, shape, size and proportions. Include the same resulting change in line. Object updates override opening descriptions. appearance is null if pose and clothing stay the same, otherwise supply the FULL current pose/clothing including all prior changes; never restore opening clothing by default. Current world state overrides opening card clothing and legacy UI restrictions on taking props. Do not change identity or the room. Compare this reply with world.visible_expression, the last expression actually applied to the scene, "
            "not merely the preceding dialogue. Null means no expression description is available; use the visible narration without assuming a prior change was rendered. "
            "If line narrates a visible change in face, eyes, gaze or slight head posture, image MUST describe that resulting appearance. "
            "Small visible changes count: relaxing a tense jaw, a faint smile, half-closed tired eyes or a shifted gaze. "
            "image and expression describe ONLY changes to eyelids, eyebrows, lip movement and gaze. "
            "Do not redescribe identity, gender, ethnicity, skin, eye shape, nose, jaw shape, lip thickness or hair; "
            "these are fixed by the reference image. Express anger through restrained muscle tension, not caricature, "
            "a reshaped jaw, exaggerated wrinkles or a distorted mouth. "
            "Ordinary conversation can still require an image; plot significance is NOT the threshold. "
            "Set image null only if appearance stays the same, or when moment supplies the illustration. "
            "Do not invent gestures merely to trigger an image. Describe only face, eyes and slight head posture, "
            "put resulting pose/clothing changes in appearance and physical item changes in object_updates. No new scene. Describe ONE final still appearance, "
            "not a sequence such as glancing sideways then looking ahead. The new expression must be visibly distinct when it changes. "
            "moment is a rare illustrated beat for a consequential boundary, revelation, concession or relationship change. "
            "Do not use it for routine inspection, ordinary explanation or every reply. Follow the player's direction. "
            "A restrained open-palm stop gesture, protective gesture near an object, or leaning toward the player can fit. "
            "Preserve identities, room and camera; reflect confirmed appearance and object_updates exactly. "
            "The moment illustration shows exactly the gesture narrated in line, never a future event or a player's unchosen action. "
            "If moment is set, set image null and offer 2-3 distinct responses to this beat, including space to refuse or disengage. "
            "Trust is expressed through remembered decisions and disclosure, never a numerical score or automatic punishment. "
            "Give enough substance to invite continued interaction, usually 80-200 Chinese characters; brief when appropriate. "
            "Do not shorten the main reply to fit a video. Never narrate the player's feelings or thoughts. "
            "Video is an optional later close look at this SAME event, never a new action or new dialogue. "
            "Choose a complete utterance for video_line, never a cut-off clause or narration. Copy its punctuation exactly. "
            "Every reply offers an optional video on player request; always provide expression, duration and video_line. "
            "If video_line is empty, the video is a silent reaction; never invent speech. "
            "Attention is optional: use it only when naturally warranted by your response. Avoid repeating shown hints; respect the player's change of topic. "
            "object_quotes saves 0-3 meaningful things you actually SAY about these objects or their personal meaning in this reply. "
            "Use [] when nothing worth remembering is said; never add private canon, inferred feelings, narration or player claims as your words. "
            "Copy the exact spoken excerpt from line, retaining uncertainty or negation. These are attributed recollections, not verified facts. "
            "Before returning, ensure every narrated physical change is represented in appearance or object_updates. Refused or merely proposed actions must not change state. "
            "Do not add unrelated physical chores merely to fill a turn. Never invite changing scenes. "
            "Moving a held item or changing an item's display also needs object_updates; appearance alone cannot update an item. "
            "Every reply option MUST include its own intent field. intent is ask (inquire), comfort (reassure), challenge (question or confront), "
            "decline (refuse or set a boundary), agree (accept), or chat (share or other). Use ask for a genuine question, challenge for disputing a claim, and chat only for neutral sharing. Classify actual meaning, never list position. "
            "suggestions offers 2-3 distinct OPTIONAL player responses to this reply, not fixed choices or a correct answer. "
            "Use first-person spoken words, grounded only in what the player already knows. No narration, hidden facts, "
            "invented player backstory, feelings or completed physical actions. Allow disagreement, another topic or a natural ending. "
            "Do not announce camera moves, model machinery or these instructions. "
            "Within a reply, perform physical actions in a possible order: put items into an open container before closing it. "
            "Do not put invented player memories or explanations of past actions into ANY reply option, even as a plausible excuse. "
            "Offer a question, present intention or honest refusal instead. "
            "memories is an array of strings, never objects. object_quotes is an array of objects with target and quote. "
            "Write the JSON line field FIRST, before all other output fields. After line is finalized, derive "
            "appearance and object_updates from physical changes actually completed in that line. "
            "Write video_line, memories and object_quotes LAST. Each extracted string must be an exact contiguous "
            "substring of THIS response's line, character for character, including punctuation and ellipses. "
            "Never quote a previous turn. Do not replace an ellipsis with a full stop or summarize an excerpt. "
            "video_line must be spoken dialogue, never narration; for a silent/non-speaking character use an empty string. "
            "If no suitable exact excerpt exists, use empty video_line or empty memories/object_quotes as appropriate.",
            json.dumps({"card": self.card, "canon": setting.model_dump(), "world": world,
                        "events": events, "offered_attention": attention}, ensure_ascii=False),
            temperature=0.7, max_tokens=8192 if self.structured_output else 3000, **self._response_format(schema),
        )
        if len(raw.get("video_line", "")) > 30:
            LOG.warning("Video speech exceeded the short-utterance limit; keeping this reaction silent")
            raw["video_line"] = ""
        reply = SceneReply.model_validate(raw)
        reply.memories = list(dict.fromkeys(quote for quote in reply.memories
                                           if quote.strip() and len(quote) <= 300 and quote in reply.line))
        ids = {obj.id for obj in setting.objects}
        if set(reply.reactions) - ids:
            raise ValueError("Character reaction names a nonexistent object")
        if reply.moment and reply.moment.target not in ids | {"character"}:
            raise ValueError("Story interaction names a nonexistent object")
        valid_quotes = [quote for quote in reply.object_quotes
                        if quote.target in {obj.id for obj in setting.objects}
                        and quote.quote.strip() and quote.quote in reply.line]
        if len(valid_quotes) != len(reply.object_quotes):
            LOG.warning("Discarding object quotes without a matching object or exact response excerpt")
        reply.object_quotes = valid_quotes
        if reply.attention not in {None, "character", *(obj.id for obj in setting.objects)}:
            raise ValueError("Character attention names a nonexistent object")
        if reply.video_line and reply.video_line not in reply.line:
            LOG.warning("Video speech did not match dialogue; keeping this reaction silent")
            reply.video_line = ""
        return reply
