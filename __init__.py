"""Read one XIT001 quarter. No watcher, no saved file, no cron job."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def _load():
    if __package__:
        from . import blueprint, schema, service
        from .messages import CREDIT
    else:
        import blueprint
        import schema
        import service
        from messages import CREDIT
    return blueprint, schema, service, CREDIT


def register(ctx) -> None:
    blueprint, schema, service, credit = _load()

    def _quarter(args, **_kwargs):
        return schema.dumps(service.quarter(args or {}))

    ctx.register_tool(
        name=service.TOOL_NAME,
        toolset=service.TOOLSET,
        schema={
            "name": service.TOOL_NAME,
            "description": (
                "Read XIT001 transaction prices (priceClassification 01, language ja) for one city, year, and quarter. "
                "city is a 5-digit code, not a municipality name. Example: 13104 is Shinjuku-ku. "
                "A designated city needs a ward code, not the city code. Example: 14101, not 14100. "
                "Returns the count, a median of digit TradePrice values, counts by Type, and at most 20 records. "
                "HTTP 404 is no data for that request, not zero rows and not unchanged prices. "
                "A city code of the right shape with no published rows is the same 404, and those two cases are not separated. "
                "Does not save a file and does not compare prices. "
                + credit
            ),
            "parameters": schema.tool_parameters(),
        },
        handler=_quarter,
    )

    def _slash_work(raw_args: str) -> str:
        parsed, detail = schema.classify_slash(raw_args or "")
        if parsed is None:
            if detail == "designated_city":
                return schema.dumps(schema.fail("bad_city"))
            return schema.dumps(schema.fail("invalid_argument", detail=detail))
        return schema.dumps(service.quarter(parsed))

    async def slash_jp_reinfolib(raw_args: str) -> str:
        return await asyncio.to_thread(_slash_work, raw_args)

    ctx.register_command(
        "jp-reinfolib",
        handler=slash_jp_reinfolib,
        description="Read one XIT001 quarter: /jp-reinfolib <city> <year> <quarter>. " + credit,
    )

    skill = Path(__file__).resolve().parent / "skills" / blueprint.SKILL_NAME / "SKILL.md"
    register_skill = getattr(ctx, "register_skill", None)
    if callable(register_skill):
        try:
            register_skill(blueprint.SKILL_NAME, skill, description="Weekly XIT001 read. Does not create a cron job.")
        except Exception:
            logger.warning("skill %s was not registered", blueprint.SKILL_NAME, exc_info=True)
    blueprint.register_blueprint(ctx)


__all__ = ["register"]
