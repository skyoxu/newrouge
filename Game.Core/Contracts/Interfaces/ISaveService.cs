using System.Threading.Tasks;
using Game.Core.Contracts.Save;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Save/continue persistence service for single-slot policy.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0007.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface ISaveService
{
    Task WriteAutosaveAsync(AutosaveSnapshot snapshot);
    Task<AutosaveSnapshot?> ReadAutosaveAsync();
    Task<ContinueMetadata?> ReadContinueMetadataAsync();
}
