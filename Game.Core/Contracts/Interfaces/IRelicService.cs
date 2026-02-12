using Game.Core.Contracts.Content;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Relic grant/query service.
/// </summary>
public interface IRelicService
{
    RelicInstance Grant(RelicDefinition definition, string source);
}

