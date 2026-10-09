"""Discovery bridge from loaded NoneBot plugins to owner declarations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from xducraft_bot.shared.configuration import (
    PluginConfiguration,
    discover_configurations,
)


@dataclass(frozen=True)
class CatalogPlugin:
    """A loaded plugin and its optional configuration declaration."""

    id: str
    short_name: str
    name: str
    description: str
    loaded: bool
    declaration: Optional[PluginConfiguration]


def discover_catalog(plugins: Iterable[Any]) -> Dict[str, CatalogPlugin]:
    """Build a catalog without importing or inventing unavailable plugins."""
    discovered = discover_configurations(plugins)
    catalog: Dict[str, CatalogPlugin] = {}
    for short_name, (plugin, declaration) in discovered.items():
        metadata = plugin.metadata
        name = declaration.name if declaration is not None else (
            str(metadata.name) if metadata is not None and metadata.name else plugin.id_
        )
        description = (
            str(metadata.description)
            if metadata is not None and metadata.description
            else ""
        )
        catalog[short_name] = CatalogPlugin(
            id=plugin.id_,
            short_name=short_name,
            name=name,
            description=description,
            loaded=True,
            declaration=declaration,
        )
    return catalog


def catalog_provider(plugins: Callable[[], Iterable[Any]]) -> Callable[[], Mapping[str, CatalogPlugin]]:
    return lambda: discover_catalog(plugins())


def build_service():
    import nonebot

    from xducraft_bot.shared import deployment_config, feature_gate

    from .service import AdminService
    from .startup import StartupResources

    return AdminService(
        catalog_provider(nonebot.get_loaded_plugins),
        feature_gate,
        deployment_config,
        nonebot.get_bots,
        startup=StartupResources(deployment_config),
    )


__all__ = ["CatalogPlugin", "build_service", "catalog_provider", "discover_catalog"]
