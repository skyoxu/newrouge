using Game.Core.Contracts.Save;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Validates or migrates autosave schema before continue entry becomes available.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0023.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public interface ISaveMigrationService
{
    SaveMigrationResult TryMigrate(string schemaVersion);
}
