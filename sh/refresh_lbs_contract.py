"""Explicitly refresh the reviewed, offline BIS LBS component/code snapshot."""

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from pysdmx.io import read_sdmx


def main():
    source = "https://stats.bis.org/api/v1/datastructure/BIS/BIS_LBS/1.0?references=all"
    request = Request(source, headers={"Accept": "application/vnd.sdmx.structure+xml;version=2.1"})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    structure = read_sdmx(io.BytesIO(payload), validate=True).get_data_structure_definitions()[0]
    if structure.id != "BIS_LBS" or structure.version != "1.0":
        raise ValueError("Unexpected BIS LBS structure version.")
    components = {}
    codelists = {}
    for component in structure.components:
        codes = component.local_codes
        code_key = f"{codes.id}({codes.version})" if codes else None
        if codes:
            codelists[code_key] = sorted(code.id for code in codes)
        components[component.id] = {
            "role": str(component.role), "required": component.required,
            "type": str(component.dtype), "codelist": code_key,
            "attachment_level": component.attachment_level,
        }
    snapshot = {
        "structure": "BIS:BIS_LBS(1.0)",
        "source": source,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "codelists": codelists,
    }
    target = Path(__file__).resolve().parents[1] / "src" / "reference_data" / "lbs_structure.json"
    target.parent.mkdir(exist_ok=True)
    json_source = "https://json.sdmx.org/2.0.0/sdmx-json-data-schema.json"
    with urlopen(json_source, timeout=60) as response:
        json_schema = response.read()
    json.loads(json_schema)
    target.with_name("sdmx_json_2_0.schema.json").write_bytes(json_schema)
    snapshot["json_schema_source"] = json_source
    snapshot["json_schema_sha256"] = hashlib.sha256(json_schema).hexdigest()
    target.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Compiled {len(components)} components and {len(codelists)} codelists to {target}.")


if __name__ == "__main__":
    main()