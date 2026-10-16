from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    # Serialization always includes the default, so the response contract requires it.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    status: Literal["ok"] = "ok"
