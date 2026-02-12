using Game.Core.Contracts.Config;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Act configuration provider.
/// </summary>
public interface IActConfigProvider
{
    ActConfig GetByActId(int actId);
}

