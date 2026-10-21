from __future__ import annotations

import re

from travel_rag.domain.models import PlanResponse

PACE_LABELS = {
    "relaxed": "舒缓",
    "balanced": "均衡",
    "intensive": "紧凑",
}
def _inline(value: object) -> str:
    text = " ".join(str(value).split())
    for character in ("\\", "`", "*", "_", "[", "]", "#", "<", ">"):
        text = text.replace(character, f"\\{character}")
    return text


def _list(values: list[str], fallback: str = "无") -> str:
    return "、".join(_inline(value) for value in values) if values else fallback


def markdown_filename(response: PlanResponse) -> str:
    destination = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", response.itinerary.destination)
    destination = destination.strip(" .-") or "travel"
    return f"{destination}-{response.itinerary.days}日旅行方案.md"


def render_plan_markdown(response: PlanResponse) -> str:
    request = response.request
    itinerary = response.itinerary

    lines = [
        f"# {_inline(itinerary.destination)} {itinerary.days} 日旅行方案",
        "",
        "## 需求概览",
        "",
        f"- **目的地：** {_inline(request.destination)}",
        f"- **行程天数：** {request.days} 天",
        f"- **预算：** ¥{request.budget_cny:,}",
        f"- **出行人群：** {_list(request.travelers)}",
        f"- **兴趣偏好：** {_list(request.interests)}",
        f"- **行程节奏：** {PACE_LABELS.get(request.pace.value, request.pace.value)}",
        f"- **限制条件：** {_list(request.constraints)}",
    ]
    if request.trip_start:
        lines.append(f"- **出发日期：** {request.trip_start.isoformat()}")

    lines.extend(
        [
            "",
            "## 逐日安排",
            "",
        ]
    )
    for day in itinerary.schedule:
        lines.extend(
            [
                f"### D{day.day} · {_inline(day.theme)}",
                "",
                f"- **上午：** {_inline(day.morning)}",
                f"- **下午：** {_inline(day.afternoon)}",
                f"- **晚间：** {_inline(day.evening)}",
                f"- **预计费用：** ¥{day.estimated_cost_cny:,}",
                "",
            ]
        )

    lines.extend(
        [
            "## 费用",
            "",
            *(
                f"- **D{day.day} · {_inline(day.theme)}：** ¥{day.estimated_cost_cny:,}"
                for day in itinerary.schedule
            ),
            "",
            f"**预计总费用：¥{itinerary.total_estimated_cost_cny:,}**",
        ]
    )
    lines.append("")
    return "\n".join(lines)
