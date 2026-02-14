using Game.Core.Contracts;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Domain event bus contract for cross-layer publish/subscribe.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface IEventBus
{
    Task PublishAsync(DomainEvent evt);

    IDisposable Subscribe(Func<DomainEvent, Task> handler);
}
