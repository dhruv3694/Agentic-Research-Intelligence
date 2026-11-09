from pydantic import BaseModel, ConfigDict, Field, field_validator


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int = Field(default=512, ge=1, le=8192)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class GenerateResponse(BaseModel):
    model: str
    response: str
    done: bool
    generation_time_ms: int


class ModelMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    format: str | None = None
    family: str | None = None
    families: list[str] | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None


class InstalledModel(BaseModel):
    name: str
    model: str
    remote_model: str | None = None
    remote_host: str | None = None
    modified_at: str | None = None
    size: int | None = None
    digest: str | None = None
    details: ModelMetadata | None = None


class ModelsResponse(BaseModel):
    models: list[InstalledModel]


class LLMStatusResponse(BaseModel):
    runtime_status: str
    connection_available: bool
    configured_model: str
    model_installed: bool | None
    message: str


class APIErrorDetail(BaseModel):
    code: str
    message: str


class APIError(BaseModel):
    error: APIErrorDetail


class OllamaModelsPayload(BaseModel):
    models: list[InstalledModel]


class OllamaGeneratePayload(BaseModel):
    response: str
    done: bool
    total_duration: int | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
