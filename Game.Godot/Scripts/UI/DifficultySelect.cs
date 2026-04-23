using System;
using System.Collections.Generic;
using System.Text.Json;
using Godot;
using Game.Core.Contracts;
using Game.Core.State;
using Game.Godot.Adapters;

namespace Game.Godot.Scripts.UI;

public partial class DifficultySelect : Control
{
    private const int MinDifficulty = 1;
    private const int MaxDifficulty = 10;
    private static readonly Dictionary<string, Dictionary<string, string>> TextMapsByLocale = new(StringComparer.OrdinalIgnoreCase);

    private Label _titleLabel = default!;
    private OptionButton _difficultyOptions = default!;
    private Label _descriptionLabel = default!;
    private Button _confirmButton = default!;

    public override void _Ready()
    {
        _titleLabel = GetNode<Label>("VBox/LblTitle");
        _difficultyOptions = GetNode<OptionButton>("VBox/DifficultyOptions");
        _descriptionLabel = GetNode<Label>("VBox/LblDescription");
        _confirmButton = GetNode<Button>("VBox/BtnConfirm");

        BuildDifficultyOptions();
        LocalizeStaticText();

        _difficultyOptions.ItemSelected += OnDifficultyItemSelected;
        _confirmButton.Pressed += OnConfirmPressed;

        SelectDifficulty(RunDifficultyState.GetConfirmedDifficulty());
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event is InputEventJoypadButton joypadButton && joypadButton.Pressed)
        {
            var buttonIndex = (int)joypadButton.ButtonIndex;
            if (buttonIndex == 13)
            {
                MoveSelection(-1);
                AcceptEvent();
                return;
            }

            if (buttonIndex == 14)
            {
                MoveSelection(1);
                AcceptEvent();
                return;
            }

            if (buttonIndex == 0)
            {
                OnConfirmPressed();
                AcceptEvent();
                return;
            }
        }

        if (@event.IsActionPressed("ui_left"))
        {
            MoveSelection(-1);
            AcceptEvent();
            return;
        }

        if (@event.IsActionPressed("ui_right"))
        {
            MoveSelection(1);
            AcceptEvent();
            return;
        }

        if (@event.IsActionPressed("ui_accept"))
        {
            OnConfirmPressed();
            AcceptEvent();
        }
    }

    public override void _GuiInput(InputEvent @event)
    {
        if (@event is InputEventMouseButton mouseButton
            && mouseButton.Pressed
            && mouseButton.ButtonIndex == MouseButton.Left)
        {
            MoveSelection(1);
            AcceptEvent();
        }
    }

    public int GetDifficultyOptionCountForTest()
    {
        return _difficultyOptions.ItemCount;
    }

    public int GetSelectedDifficultyForTest()
    {
        return GetSelectedDifficulty();
    }

    public int GetConfirmedDifficultyForTest()
    {
        return RunDifficultyState.GetConfirmedDifficulty();
    }

    public string GetControlShapeForTest()
    {
        return "button_group";
    }

    public bool IsSelectionIndicatorVisibleForTest()
    {
        return _difficultyOptions.Visible && Visible;
    }

    public void SelectDifficultyForTest(int difficultyId)
    {
        SelectDifficulty(difficultyId);
    }

    public void NavigateKeyboardForTest(int step)
    {
        SelectDifficulty(GetSelectedDifficulty() + step);
    }

    public void NavigateMouseForTest(int difficultyId)
    {
        SelectDifficulty(difficultyId);
    }

    public void NavigateGamepadForTest(int step)
    {
        SelectDifficulty(GetSelectedDifficulty() + step);
    }

    public void ConfirmSelectionForTest()
    {
        OnConfirmPressed();
    }

    public void ResetConfirmedDifficultyForTest(int difficultyId)
    {
        RunDifficultyState.SetConfirmedDifficulty(ClampDifficulty(difficultyId));
        SelectDifficulty(RunDifficultyState.GetConfirmedDifficulty());
    }

    public string GetDescriptionKeyForTest(int difficultyId)
    {
        return BuildDescriptionKey(ClampDifficulty(difficultyId));
    }

    public string GetDescriptionTextForTest(int difficultyId)
    {
        var key = GetDescriptionKeyForTest(difficultyId);
        return ResolveVisibleText(key);
    }

    public bool HasDescriptionTranslationForTest(int difficultyId)
    {
        var key = GetDescriptionKeyForTest(difficultyId);
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        return GetTextMap(locale).ContainsKey(key) || GetTextMap("en").ContainsKey(key);
    }

    public void RefreshLocaleForTest()
    {
        BuildDifficultyOptions();
        LocalizeStaticText();
        SelectDifficulty(RunDifficultyState.GetConfirmedDifficulty());
    }

    public void RefreshVisibleTextForTest()
    {
        RefreshLocaleForTest();
    }

    private void BuildDifficultyOptions()
    {
        _difficultyOptions.Clear();
        for (var difficulty = MinDifficulty; difficulty <= MaxDifficulty; difficulty++)
        {
            var key = $"ui.difficulty.{difficulty}";
            _difficultyOptions.AddItem(ResolveVisibleText(key), difficulty);
        }
    }

    private void LocalizeStaticText()
    {
        _titleLabel.Text = ResolveVisibleText("ui.difficulty.title");
        _confirmButton.Text = ResolveVisibleText("ui.difficulty.confirm");
    }

    private void OnDifficultyItemSelected(long _index)
    {
        UpdateDescriptionLabel(GetSelectedDifficulty());
    }

    private void OnConfirmPressed()
    {
        var selected = GetSelectedDifficulty();
        RunDifficultyState.SetConfirmedDifficulty(selected);
        PublishDifficultySelected(selected);
    }

    private void MoveSelection(int step)
    {
        SelectDifficulty(GetSelectedDifficulty() + step);
    }

    private void SelectDifficulty(int difficultyId)
    {
        var target = ClampDifficulty(difficultyId);
        var targetIndex = -1;
        for (var i = 0; i < _difficultyOptions.ItemCount; i++)
        {
            if (_difficultyOptions.GetItemId(i) == target)
            {
                targetIndex = i;
                break;
            }
        }

        if (targetIndex < 0)
        {
            targetIndex = 0;
        }

        _difficultyOptions.Select(targetIndex);
        UpdateDescriptionLabel(target);
    }

    private int GetSelectedDifficulty()
    {
        var selected = _difficultyOptions.Selected;
        if (selected < 0 || selected >= _difficultyOptions.ItemCount)
        {
            return MinDifficulty;
        }

        return _difficultyOptions.GetItemId(selected);
    }

    private void UpdateDescriptionLabel(int difficultyId)
    {
        var key = BuildDescriptionKey(ClampDifficulty(difficultyId));
        _descriptionLabel.Text = ResolveVisibleText(key);
    }

    private static int ClampDifficulty(int difficultyId)
    {
        return Math.Clamp(difficultyId, MinDifficulty, MaxDifficulty);
    }

    private static string BuildDescriptionKey(int difficultyId)
    {
        return $"ui.difficulty.{difficultyId}.desc";
    }

    private static string ResolveVisibleText(string keyOrText)
    {
        if (string.IsNullOrWhiteSpace(keyOrText))
        {
            return string.Empty;
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

        var localized = TranslationServer.Translate(keyOrText);
        return string.Equals(localized, keyOrText, StringComparison.Ordinal) ? keyOrText : localized;
    }

    private static Dictionary<string, string> GetTextMap(string locale)
    {
        if (TextMapsByLocale.TryGetValue(locale, out var cached))
        {
            return cached;
        }

        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var candidatePaths = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? new[] { "res://Game.Godot/Translations/zh-CN.csv", "res://../Game.Godot/Translations/zh-CN.csv" }
            : new[] { "res://Game.Godot/Translations/en.csv", "res://../Game.Godot/Translations/en.csv" };

        string raw = string.Empty;
        foreach (var candidatePath in candidatePaths)
        {
            if (!FileAccess.FileExists(candidatePath))
            {
                continue;
            }

            using var file = FileAccess.Open(candidatePath, FileAccess.ModeFlags.Read);
            if (file is null)
            {
                continue;
            }

            raw = file.GetAsText();
            break;
        }

        if (string.IsNullOrWhiteSpace(raw))
        {
            TextMapsByLocale[locale] = map;
            return map;
        }

        foreach (var line in raw.Split('\n', StringSplitOptions.RemoveEmptyEntries))
        {
            var trimmed = line.Trim();
            if (string.IsNullOrWhiteSpace(trimmed) || trimmed.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var sep = trimmed.IndexOf(',');
            if (sep <= 0 || sep >= trimmed.Length - 1)
            {
                continue;
            }

            var key = trimmed[..sep].Trim();
            var value = trimmed[(sep + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key) && !string.IsNullOrWhiteSpace(value))
            {
                map[key] = value;
            }
        }

        TextMapsByLocale[locale] = map;
        return map;
    }

    private static string NormalizeLocale(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return "en";
        }

        return locale.Trim().Replace('_', '-').ToLowerInvariant();
    }

    private void PublishDifficultySelected(int difficultyId)
    {
        var bus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        if (bus is null)
        {
            return;
        }

        var payload = JsonSerializer.Serialize(new
        {
            difficulty_id = difficultyId
        });
        bus.PublishSimple(EventTypes.RunDifficultySelected, "ui.difficulty.select", payload);
    }
}
