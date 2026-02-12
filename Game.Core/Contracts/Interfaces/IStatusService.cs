using Game.Core.Contracts.Status;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Status apply/stack/expire operations.
/// </summary>
public interface IStatusService
{
    StatusInstance Apply(StatusInstance current, StatusInstance incoming);
    StatusInstance Tick(StatusInstance current, ExpiresTiming timing);
}

