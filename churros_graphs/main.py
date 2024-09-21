import json
import re
import subprocess
from typing import Any
from pathlib import Path

import requests

if not Path("querycache.json").exists():
    Path("querycache.json").write_text("{}")

def readable_text_color_on(color_hexstring: str) -> str:
    r, g, b = (int(color_hexstring[i : i + 2], 16) for i in range(1, 7, 2))
    return "#000000" if r * 0.299 + g * 0.587 + b * 0.114 > 186 else "#ffffff"


types = ["Association", "Club", "StudentAssociationSection"]
show_labels = True
querycache = json.loads(Path("querycache.json").read_text())


def gql(query: str, variables: dict[str, Any] = None) -> dict[str, Any]:
    query = query.replace("query ", "query ChurrosGraphs_")
    if (queryhash := (query.replace(" ", "") + json.dumps(variables))) in querycache:
        return querycache[queryhash]
    response = requests.post(
        "https://churros.inpt.fr/graphql",
        json={
            "query": query,
            "operationName": re.search(r"query (\w+)(?:\(.*\))? \{", query).group(1),
            "variables": variables or {},
        },
    ).json()
    querycache[queryhash] = response
    Path("querycache.json").write_text(json.dumps(querycache))
    return response


colors = {}


def memberships():
    return gql(
        """
        query Memberships($types: [GroupType!]!) {
            groups(types: $types) {
                name
                color
                boardMembers {
                    member {
                        groups {
                            president, secretary, treasurer, vicePresident, title
                            member{uid, yearTier}
                            group {
                                type
                                name
                            }
                        }
                    }
                }
            }
        }    
    """,
        {"types": types},
    )


def is_board_membership(membership: dict[str, Any]) -> bool:
    # return membership["title"] != "Membre"
    return any(
        membership.get(role)
        for role in ["president", "secretary", "treasurer", "vicePresident"]
    )


if __name__ == "__main__":
    relationships = memberships()

    arrows: list[tuple[str, str, str]] = []

    for group in relationships["data"]["groups"]:
        colors[group["name"]] = group["color"]
        for board_member in group["boardMembers"]:
            for membership in board_member["member"]["groups"]:
                if (
                    membership["group"]["type"] in types
                    and is_board_membership(membership)
                    and membership["member"]["yearTier"] <= 3
                ):
                    arrows.append(
                        (
                            group["name"],
                            membership["member"]["uid"],
                            membership["group"]["name"],
                        )
                    )

    # remove duplicate arrows
    deduplicated = []
    # people that cause an arrow, format: uid1:uid2 -> people uids
    causes: dict[str, list[str]] = {}
    causekey = lambda a, b: f"{':'.join(sorted([a, b]))}"
    for start, by, end in arrows:
        if start != end:
            causes.setdefault(causekey(start, end), []).append(by)
        if (
            (start, end) not in deduplicated
            and start != end
            and (end, start) not in deduplicated
        ):
            deduplicated.append((start, end))

    print(causes)
    Path("./graph.dot").write_text(
        "graph G {\n"
        + "overlap=false;\n"
        + 'sep="+10";\n'
        + "{"
        + "\n".join(
            f'    "{name}" [shape=box  style=filled  fillcolor="{color}" fontcolor="{readable_text_color_on(color)}"];'
            for name, color in colors.items()
            if name in {a for a, b in deduplicated} | {b for a, b in deduplicated}
        )
        + "}\n"
        + "\n".join(
            f'    "{a}" -- "{b}" [label="{', '.join(set(causes.get(causekey(a, b), [])))}"];'
            if show_labels
            else f'    "{a}" -- "{b}" ;'
            for a, b in deduplicated
        )
        + "\n}"
    )

    for fmt in ['png', 'svg']:
        subprocess.run(
            ["dot", "-K", "neato", "-v", f"-T{fmt}", "graph.dot", "-o", f"graph.{fmt}"]
        )
