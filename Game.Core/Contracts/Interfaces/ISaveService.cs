using Game.Core.Contracts.Save;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Save/continue persistence service for single-slot policy.
/// </summary>
public interface ISaveService
{
    void WriteAutosave(AutosaveSnapshot snapshot);
    AutosaveSnapshot? ReadAutosave();
    ContinueMetadata? ReadContinueMetadata();
}

