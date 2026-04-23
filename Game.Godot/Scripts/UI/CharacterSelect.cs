using System;
using System.Collections.Generic;
using System.Text.Json;
using Godot;
using Game.Core.Contracts;
using Game.Godot.Adapters;

namespace Game.Godot.Scripts.UI;

public partial class CharacterSelect : Control
{
    private const string WarriorId = "warrior";
    private const string MageId = "mage";
    private const string RogueId = "rogue";

    private static readonly StringComparer IdComparer = StringComparer.OrdinalIgnoreCase;
    private static readonly Dictionary<string, string> LockLabelKeys = new(IdComparer)
    {
        [MageId] = "ui.character.not_open",
        [RogueId] = "ui.character.not_open"
    };

    private static readonly string[] WarriorSummaryKeys =
    {
        "ui.character.warrior.summary.rage_buff",
        "ui.character.warrior.summary.power_window",
        "ui.character.warrior.summary.cost_burst"
    };

    private static readonly Dictionary<string, Dictionary<string, string>> TextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);

    private Button _btnWarrior = default!;
    private Button _btnMage = default!;
    private Button _btnRogue = default!;
    private Label _lblTitle = default!;
    private Label _lblMageLock = default!;
    private Label _lblRogueLock = default!;
    private Label _lblWarriorState = default!;
    private Label _lblSummary1 = default!;
    private Label _lblSummary2 = default!;
    private Label _lblSummary3 = default!;
    private string _selectedCharacterId = WarriorId;
    private string _lastLocale = string.Empty;

    public override void _Ready()
    {
        _btnWarrior = GetNode<Button>("VBox/CharacterRow/WarriorPanel/BtnWarrior");
        _btnMage = GetNode<Button>("VBox/CharacterRow/MagePanel/BtnMage");
        _btnRogue = GetNode<Button>("VBox/CharacterRow/RoguePanel/BtnRogue");
        _lblTitle = GetNode<Label>("VBox/LblTitle");
        _lblMageLock = GetNode<Label>("VBox/CharacterRow/MagePanel/LblMageLock");
        _lblRogueLock = GetNode<Label>("VBox/CharacterRow/RoguePanel/LblRogueLock");
        _lblWarriorState = GetNode<Label>("VBox/CharacterRow/WarriorPanel/LblWarriorState");
        _lblSummary1 = GetNode<Label>("VBox/Summary/LblSummaryLine1");
        _lblSummary2 = GetNode<Label>("VBox/Summary/LblSummaryLine2");
        _lblSummary3 = GetNode<Label>("VBox/Summary/LblSummaryLine3");

        _btnWarrior.Pressed += () => TrySelectCharacter(WarriorId);
        _btnMage.Pressed += () => TrySelectCharacter(MageId);
        _btnRogue.Pressed += () => TrySelectCharacter(RogueId);

        ApplyCharacterState();
        RefreshLocalizedText(force: true);
    }

    public override void _Process(double _delta)
    {
        RefreshLocalizedText(force: false);
    }

    public void SelectCharacterForTest(string characterId)
    {
        TrySelectCharacter(characterId);
    }

    public void KeyboardConfirmCharacterForTest(string characterId)
    {
        var normalized = NormalizeId(characterId);
        if (!string.Equals(normalized, WarriorId, StringComparison.Ordinal))
        {
            return;
        }

        TrySelectCharacter(normalized);
        ConfirmSelectedCharacterForTest();
    }

    public string GetSelectedCharacterForTest()
    {
        return _selectedCharacterId;
    }

    public bool IsCharacterInteractableForTest(string characterId)
    {
        return string.Equals(NormalizeId(characterId), WarriorId, StringComparison.Ordinal);
    }

    public bool IsCharacterHiddenOrDimmedForTest(string characterId)
    {
        return !IsCharacterInteractableForTest(characterId);
    }

    public string GetLockLabelKeyForTest(string characterId)
    {
        var normalized = NormalizeId(characterId);
        return LockLabelKeys.TryGetValue(normalized, out var key) ? key : string.Empty;
    }

    public string GetLockLabelTextForTest(string characterId)
    {
        RefreshLocalizedText(force: false);
        var key = GetLockLabelKeyForTest(characterId);
        return string.IsNullOrWhiteSpace(key) ? string.Empty : ResolveVisibleText(key);
    }

    public global::Godot.Collections.Array<string> GetWarriorSummaryLinesForTest()
    {
        RefreshLocalizedText(force: false);
        return new global::Godot.Collections.Array<string>
        {
            _lblSummary1.Text,
            _lblSummary2.Text,
            _lblSummary3.Text
        };
    }

    public global::Godot.Collections.Array<string> GetWarriorSummaryKeysForTest()
    {
        return new global::Godot.Collections.Array<string>
        {
            WarriorSummaryKeys[0],
            WarriorSummaryKeys[1],
            WarriorSummaryKeys[2]
        };
    }

    public string GetLocalizedTextByKeyForTest(string key)
    {
        RefreshLocalizedText(force: false);
        return ResolveVisibleText(key);
    }

    public void ConfirmSelectedCharacterForTest()
    {
        PublishCharacterSelected(_selectedCharacterId);
    }

    public void RefreshLocaleForTest()
    {
        RefreshLocalizedText(force: true);
    }

    private void TrySelectCharacter(string characterId)
    {
        var normalized = NormalizeId(characterId);
        if (!string.Equals(normalized, WarriorId, StringComparison.Ordinal))
        {
            return;
        }

        _selectedCharacterId = WarriorId;
        ApplyCharacterState();
    }

    private void ApplyCharacterState()
    {
        _btnWarrior.Disabled = false;
        _btnMage.Disabled = true;
        _btnRogue.Disabled = true;

        _btnWarrior.Modulate = Colors.White;
        _btnMage.Modulate = new Color(1f, 1f, 1f, 0.55f);
        _btnRogue.Modulate = new Color(1f, 1f, 1f, 0.55f);

        _lblWarriorState.Visible = true;
        _lblWarriorState.Text = _selectedCharacterId == WarriorId ? ResolveVisibleText("ui.character.selected") : string.Empty;

        _lblMageLock.Visible = true;
        _lblRogueLock.Visible = true;
    }

    private void RefreshLocalizedText(bool force)
    {
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        if (!force && string.Equals(locale, _lastLocale, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        _lastLocale = locale;

        _lblTitle.Text = ResolveVisibleText("ui.character.select.title");
        _btnWarrior.Text = ResolveVisibleText("ui.character.warrior");
        _btnMage.Text = ResolveVisibleText("ui.character.mage");
        _btnRogue.Text = ResolveVisibleText("ui.character.rogue");
        _lblWarriorState.Text = _selectedCharacterId == WarriorId ? ResolveVisibleText("ui.character.selected") : string.Empty;

        _lblMageLock.Text = ResolveVisibleText("ui.character.not_open");
        _lblRogueLock.Text = ResolveVisibleText("ui.character.not_open");

        _lblSummary1.Text = ResolveVisibleText(WarriorSummaryKeys[0]);
        _lblSummary2.Text = ResolveVisibleText(WarriorSummaryKeys[1]);
        _lblSummary3.Text = ResolveVisibleText(WarriorSummaryKeys[2]);
    }

    private static string ResolveVisibleText(string keyOrText)
    {
        if (string.IsNullOrWhiteSpace(keyOrText))
        {
            return string.Empty;
        }

        var localized = TranslationServer.Translate(keyOrText);
        if (!string.Equals(localized, keyOrText, StringComparison.Ordinal))
        {
            return localized;
        }

        var locale = NormalizeLocale(TranslationServer.GetLocale());
        var map = GetTextMap(locale);
        if (map.TryGetValue(keyOrText, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        if (!string.Equals(locale, "en", StringComparison.OrdinalIgnoreCase))
        {
            var fallback = GetTextMap("en");
            if (fallback.TryGetValue(keyOrText, out var fallbackValue) && !string.IsNullOrWhiteSpace(fallbackValue))
            {
                return fallbackValue;
            }
        }

        return keyOrText;
    }

    private static Dictionary<string, string> GetTextMap(string locale)
    {
        if (TextMapsByLocale.TryGetValue(locale, out var cached))
        {
            return cached;
        }

        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var path = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "res://Game.Godot/Translations/zh-CN.csv"
            : "res://Game.Godot/Translations/en.csv";

        if (!FileAccess.FileExists(path))
        {
            TextMapsByLocale[locale] = map;
            return map;
        }

        using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            TextMapsByLocale[locale] = map;
            return map;
        }

        var raw = file.GetAsText();
        var lines = raw.Split('\n', StringSplitOptions.RemoveEmptyEntries);
        foreach (var rawLine in lines)
        {
            var line = rawLine.Trim();
            if (string.IsNullOrWhiteSpace(line) || line.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var comma = line.IndexOf(',');
            if (comma <= 0 || comma >= line.Length - 1)
            {
                continue;
            }

            var key = line[..comma].Trim();
            var value = line[(comma + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key) && !string.IsNullOrWhiteSpace(value))
            {
                map[key] = value;
            }
        }

        TextMapsByLocale[locale] = map;
        return map;
    }

    private static string NormalizeId(string characterId)
    {
        return string.IsNullOrWhiteSpace(characterId)
            ? string.Empty
            : characterId.Trim().ToLowerInvariant();
    }

    private static string NormalizeLocale(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return "en";
        }

        var normalized = locale.Trim().Replace('_', '-');
        return normalized.ToLowerInvariant();
    }

    private void PublishCharacterSelected(string characterId)
    {
        var bus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        if (bus is null)
        {
            return;
        }

        var payload = JsonSerializer.Serialize(new
        {
            character_id = characterId
        });
        bus.PublishSimple(EventTypes.RunCharacterSelected, "ui.character.select", payload);
    }
}
