"""
ConfigurationManager — loads, validates, and hot-reloads application configuration.

Supports JSON and YAML config files in a designated directory.
Validates all parameters against defined ranges before applying them.
Retains the previous valid configuration on reload failure.

Requirements: 5.1–5.13
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import ValidationError

from app.models.models import AppConfig

logger = logging.getLogger(__name__)

# Maximum wall-clock seconds allowed for a single reload operation (Req 5.7)
_RELOAD_TIMEOUT_SECONDS = 5.0


class ConfigurationError(Exception):
    """Raised when configuration validation fails.

    Attributes
    ----------
    parameter : str
        Dot-notation name of the failing parameter (e.g. ``"chunking.chunk_size_tokens"``).
    message : str
        Human-readable description of why the parameter failed.
    """

    def __init__(self, parameter: str, message: str) -> None:
        self.parameter = parameter
        self.message = message
        super().__init__(f"Configuration error for '{parameter}': {message}")


@dataclass
class ReloadResult:
    """Outcome of a :meth:`ConfigurationManager.reload` call.

    Attributes
    ----------
    success : bool
        ``True`` if the new configuration was applied; ``False`` if the reload
        failed and the previous configuration was retained.
    config : Optional[AppConfig]
        The newly applied configuration when ``success`` is ``True``, otherwise
        ``None``.
    error : Optional[str]
        Human-readable error description when ``success`` is ``False``.
    parameter : Optional[str]
        The failing parameter name when the reload failed due to validation.
    elapsed_seconds : float
        Wall-clock time (in seconds) spent on the reload attempt.
    """

    success: bool
    config: Optional[AppConfig] = None
    error: Optional[str] = None
    parameter: Optional[str] = None
    elapsed_seconds: float = 0.0


class ConfigurationManager:
    """Loads and manages application configuration from JSON/YAML files.

    Parameters
    ----------
    config_dir : str
        Path to the directory that contains ``.json``, ``.yaml``, or ``.yml``
        configuration files.  All matching files are merged in alphabetical
        order (later files override earlier ones).

    Usage
    -----
    ::

        cm = ConfigurationManager("/app/config")
        cfg = cm.load()
        value = cm.get("chunking.chunk_size_tokens")
        result = cm.reload()
    """

    def __init__(self, config_dir: str) -> None:
        self._config_dir = Path(config_dir)
        self._current_config: Optional[AppConfig] = None
        # Re-entrant lock so that reload can safely swap the active config
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> AppConfig:
        """Load and validate configuration from *config_dir*.

        Reads every ``.json``, ``.yaml``, and ``.yml`` file in
        :attr:`config_dir` (alphabetically), merges them into a single
        mapping, validates with Pydantic, and stores the result as the
        active configuration.

        Returns
        -------
        AppConfig
            The validated, active configuration.

        Raises
        ------
        ConfigurationError
            If any parameter fails validation, naming the specific parameter.
        FileNotFoundError
            If *config_dir* does not exist or contains no config files.
        """
        raw = self._read_and_merge_files()
        config = self._validate(raw)
        with self._lock:
            self._current_config = config
        logger.info("Configuration loaded successfully from '%s'.", self._config_dir)
        return config

    def reload(self) -> ReloadResult:
        """Hot-reload configuration from *config_dir*, completing within 5 s.

        If the new configuration fails validation the previous valid
        configuration is retained and the returned :class:`ReloadResult` has
        ``success=False``.

        Returns
        -------
        ReloadResult
            Outcome of the reload attempt.
        """
        start = time.monotonic()

        # Run the actual reload work in a container we can time-box
        result_holder: list[ReloadResult] = []
        exception_holder: list[BaseException] = []

        def _do_reload() -> None:
            try:
                raw = self._read_and_merge_files()
                config = self._validate(raw)
                result_holder.append(
                    ReloadResult(success=True, config=config)
                )
            except (ConfigurationError, FileNotFoundError, OSError) as exc:
                result_holder.append(
                    ReloadResult(
                        success=False,
                        error=str(exc),
                        parameter=exc.parameter if isinstance(exc, ConfigurationError) else None,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                exception_holder.append(exc)

        worker = threading.Thread(target=_do_reload, daemon=True)
        worker.start()
        worker.join(timeout=_RELOAD_TIMEOUT_SECONDS)

        elapsed = time.monotonic() - start

        if worker.is_alive():
            # Timed out — retain current config
            logger.error(
                "Configuration reload timed out after %.2f s; retaining previous config.",
                elapsed,
            )
            return ReloadResult(
                success=False,
                error=f"Reload timed out after {elapsed:.2f} s (limit {_RELOAD_TIMEOUT_SECONDS} s).",
                elapsed_seconds=elapsed,
            )

        if exception_holder:
            err_msg = f"Unexpected error during reload: {exception_holder[0]}"
            logger.error(err_msg, exc_info=exception_holder[0])
            return ReloadResult(
                success=False,
                error=err_msg,
                elapsed_seconds=elapsed,
            )

        result = result_holder[0]
        result.elapsed_seconds = elapsed

        if result.success:
            with self._lock:
                self._current_config = result.config
            logger.info(
                "Configuration reloaded successfully in %.3f s.", elapsed
            )
        else:
            logger.error(
                "Configuration reload failed (%.3f s): %s; retaining previous config.",
                elapsed,
                result.error,
            )

        return result

    def get(self, key: str) -> Any:
        """Return the value for a dot-notation configuration key.

        Parameters
        ----------
        key : str
            Dot-separated path into the active configuration, e.g.
            ``"chunking.chunk_size_tokens"`` or ``"reranker.reranker_provider"``.

        Returns
        -------
        Any
            The value at *key*.

        Raises
        ------
        RuntimeError
            If configuration has not been loaded yet.
        KeyError
            If *key* does not exist in the active configuration.
        """
        with self._lock:
            config = self._current_config

        if config is None:
            raise RuntimeError(
                "Configuration has not been loaded. Call load() first."
            )

        # Walk the dot-notation path through the nested Pydantic model
        parts = key.split(".")
        current: Any = config
        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    raise KeyError(
                        f"Configuration key '{key}' not found (missing segment '{part}')."
                    )
                current = current[part]
            else:
                # Pydantic model or plain object attribute access
                if not hasattr(current, part):
                    raise KeyError(
                        f"Configuration key '{key}' not found (missing segment '{part}')."
                    )
                current = getattr(current, part)

        return current

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_and_merge_files(self) -> dict:
        """Read and merge all JSON/YAML files from *config_dir*.

        Files are processed in alphabetical order; later files override
        earlier ones for duplicate keys (shallow merge at the top level,
        deep merge for nested dicts).

        Returns
        -------
        dict
            Merged raw configuration mapping.

        Raises
        ------
        FileNotFoundError
            If *config_dir* does not exist or no config files are found.
        """
        if not self._config_dir.exists():
            raise FileNotFoundError(
                f"Configuration directory '{self._config_dir}' does not exist."
            )

        config_files = sorted(
            [
                p
                for p in self._config_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".json", ".yaml", ".yml"}
            ]
        )

        if not config_files:
            raise FileNotFoundError(
                f"No JSON or YAML configuration files found in '{self._config_dir}'."
            )

        merged: dict = {}
        for filepath in config_files:
            logger.debug("Reading config file: %s", filepath)
            raw = self._parse_file(filepath)
            _deep_merge(merged, raw)

        return merged

    @staticmethod
    def _parse_file(filepath: Path) -> dict:
        """Parse a single JSON or YAML file.

        Parameters
        ----------
        filepath : Path
            Path to the config file.

        Returns
        -------
        dict
            Parsed content.

        Raises
        ------
        ValueError
            If the file cannot be parsed or does not contain a mapping.
        """
        text = filepath.read_text(encoding="utf-8")
        suffix = filepath.suffix.lower()

        try:
            if suffix == ".json":
                data = json.loads(text)
            else:  # .yaml / .yml
                data = yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ValueError(
                f"Failed to parse config file '{filepath}': {exc}"
            ) from exc

        if data is None:
            # Empty YAML file — treat as empty dict
            return {}

        if not isinstance(data, dict):
            raise ValueError(
                f"Config file '{filepath}' must contain a YAML/JSON mapping at the top level, "
                f"got {type(data).__name__}."
            )

        return data

    @staticmethod
    def _validate(raw: dict) -> AppConfig:
        """Validate the raw mapping and return an :class:`AppConfig`.

        Parameters
        ----------
        raw : dict
            Merged raw configuration dict (from files on disk).

        Returns
        -------
        AppConfig
            The validated configuration.

        Raises
        ------
        ConfigurationError
            Naming the first failing parameter if any Pydantic validation
            fails.
        """
        try:
            return AppConfig.model_validate(raw)
        except ValidationError as exc:
            # Extract the first error and map it to a ConfigurationError
            first_error = exc.errors()[0]
            # loc is a tuple of field path segments, e.g. ('chunking', 'chunk_size_tokens')
            loc = first_error.get("loc", ())
            param_name = ".".join(str(s) for s in loc) if loc else "unknown"
            msg = first_error.get("msg", "Validation failed")
            raise ConfigurationError(parameter=param_name, message=msg) from exc


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge *override* into *base* in-place.

    Nested dicts are merged recursively; all other values are replaced by
    the value from *override*.
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
