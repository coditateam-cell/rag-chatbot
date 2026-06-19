import json
import tempfile
from pathlib import Path
from app.config.configuration_manager import ConfigurationManager

def test_config_optional_field_defaults() -> None:
    """Verify that when optional fields are omitted from configuration files,

    ConfigurationManager applies defined default values.
    Validates Requirement 5.12.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a minimal config file with empty dictionary
        config_file = Path(tmp_dir) / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        cm = ConfigurationManager(tmp_dir)
        config = cm.load()

        # Assert default values are applied
        assert config.prompt_templates.system_instructions == (
            "You are a helpful assistant that answers questions based on the provided document context."
        )
        assert config.chunking.chunk_size_tokens == 400
        assert config.chunking.overlap_percentage == 12.0
        assert config.chunking.enable_contextual_summaries is True
        assert config.models.llm_model_name == "openai/gpt-4o"
        assert config.models.embedding_model_name == "openai/text-embedding-3-small"
        assert config.reranker.reranker_provider == "cohere"
        assert config.reranker.reranker_model_name == "rerank-english-v3.0"
        assert config.reranker.reranker_top_k == 5
        assert config.retrieval.top_k == 20
        assert config.retrieval.similarity_threshold == 0.7
        assert config.retrieval.max_chunks_evaluated == 100
        assert config.retrieval.prompt_max_chars == 8000
