using System;
using System.Collections.Generic;
using System.Text.Json;
using Godot;
using Game.Core.Contracts;
using Game.Godot.Adapters;

namespace Game.Godot.Scripts.UI;

public partial class MainMenu : Control
{
    private static readonly JsonDocumentOptions AutosaveJsonOptions = new()
    {
        MaxDepth = 16
    };

    private Button _btnNewRun = default!;
    private Button _btnContinue = default!;
    private Button _btnQuit = default!;
    private ConfirmationDialog? _overwriteConfirmDialog;
    private bool? _autosaveAvailableOverride;
    private bool _disableQuitForTests;
    private bool _quitRequested;
    private bool _quitIntentReachedForTest;
    private bool _hasQuitRequestCallbackForTest;
    private Callable _quitRequestCallbackForTest;
    private string _lastDialogFocusPreferenceForTest = string.Empty;
    private static Dictionary<string, string>? _menuTextFallbacks;
    private string _lastLocaleForRuntimeRefresh = string.Empty;

    public override void _Ready()
    {
        _btnNewRun = GetNode<Button>("VBox/BtnNewRun");
        _btnContinue = GetNode<Button>("VBox/BtnContinue");
        _btnQuit = GetNode<Button>("VBox/BtnQuit");
        _overwriteConfirmDialog = GetNodeOrNull<ConfirmationDialog>("OverwriteConfirmDialog");

        LocalizeVisibleText();
        RefreshContinueAvailability();

        _btnNewRun.Pressed += OnNewRunPressed;
        _btnContinue.Pressed += OnContinuePressed;
        _btnQuit.Pressed += OnQuitPressed;
        if (_overwriteConfirmDialog is not null)
        {
            _overwriteConfirmDialog.Confirmed += OnOverwriteConfirmed;
            _overwriteConfirmDialog.Canceled += OnOverwriteCanceled;
        }

        _lastLocaleForRuntimeRefresh = NormalizeLocale(TranslationServer.GetLocale());
    }

    public override void _Process(double _delta)
    {
        var locale = NormalizeLocale(TranslationServer.GetLocale());
        if (string.Equals(locale, _lastLocaleForRuntimeRefresh, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        _lastLocaleForRuntimeRefresh = locale;
        _menuTextFallbacks = null;
        LocalizeVisibleText();
    }

    public void ShowMenu() => Visible = true;
    public void HideMenu() => Visible = false;
    public void SetAutosaveAvailableForTest(bool value)
    {
        _autosaveAvailableOverride = value;
        RefreshContinueAvailability();
    }

    public void SetDisableQuitForTests(bool value)
    {
        _disableQuitForTests = value;
    }

    public bool WasQuitRequestedForTest()
    {
        return _quitRequested;
    }

    public bool WasQuitIntentReachedForTest()
    {
        return _quitIntentReachedForTest;
    }

    public string GetLastDialogFocusPreferenceForTest()
    {
        return _lastDialogFocusPreferenceForTest;
    }

    public void SetQuitRequestCallbackForTest(Callable callback)
    {
        _quitRequestCallbackForTest = callback;
        _hasQuitRequestCallbackForTest = true;
    }

    public void RefreshVisibleTextForTest()
    {
        _menuTextFallbacks = null;
        LocalizeVisibleText();
    }

    private void LocalizeVisibleText()
    {
        _btnNewRun.Text = ResolveVisibleText(_btnNewRun.Text);
        _btnContinue.Text = ResolveVisibleText(_btnContinue.Text);
        _btnQuit.Text = ResolveVisibleText(_btnQuit.Text);

        if (_overwriteConfirmDialog is null)
        {
            return;
        }

        _overwriteConfirmDialog.Title = ResolveVisibleText(_overwriteConfirmDialog.Title);
        _overwriteConfirmDialog.DialogText = ResolveVisibleText(_overwriteConfirmDialog.DialogText);
        _overwriteConfirmDialog.OkButtonText = ResolveVisibleText(_overwriteConfirmDialog.OkButtonText);
        _overwriteConfirmDialog.CancelButtonText = ResolveVisibleText(_overwriteConfirmDialog.CancelButtonText);
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

        var fallback = ResolveTextFromTranslationFiles(keyOrText);
        return fallback;
    }

    private static string ResolveTextFromTranslationFiles(string keyOrText)
    {
        _menuTextFallbacks ??= LoadMenuTextFallbacks();
        if (_menuTextFallbacks.TryGetValue(keyOrText, out var value) && !string.IsNullOrWhiteSpace(value))
        {
            return value;
        }

        return keyOrText;
    }

    private static Dictionary<string, string> LoadMenuTextFallbacks()
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        var locale = TranslationServer.GetLocale();
        var preferred = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? "res://Game.Godot/Translations/zh-CN.csv"
            : "res://Game.Godot/Translations/en.csv";
        var path = preferred;
        if (!FileAccess.FileExists(path))
        {
            path = "res://Game.Godot/Translations/en.csv";
        }

        if (!FileAccess.FileExists(path))
        {
            return map;
        }

        using var file = FileAccess.Open(path, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return map;
        }

        var raw = file.GetAsText();
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

    private void Publish(string type, string source, string dataJson = "{}")
    {
        var bus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        bus?.PublishSimple(type, source, dataJson);
    }

    private void RefreshContinueAvailability()
    {
        _btnContinue.Disabled = !HasValidAutosave();
    }

    private bool HasValidAutosave()
    {
        if (_autosaveAvailableOverride.HasValue)
        {
            return _autosaveAvailableOverride.Value;
        }

        using var file = FileAccess.Open("user://autosave_slot.json", FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return false;
        }

        var text = file.GetAsText().Trim();
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        try
        {
            using var document = JsonDocument.Parse(text, AutosaveJsonOptions);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
            {
                return false;
            }

            return HasRequiredString(root, "run_id")
                && HasRequiredString(root, "save_point_id")
                && HasRequiredString(root, "schema_version")
                && HasRequiredString(root, "state_json")
                && HasRequiredString(root, "integrity_hash")
                && HasRequiredDateTimeOffset(root, "saved_at");
        }
        catch (JsonException)
        {
            return false;
        }
    }

    private static bool HasRequiredString(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out var value)
            && value.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(value.GetString());
    }

    private static bool HasRequiredDateTimeOffset(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        return DateTimeOffset.TryParse(value.GetString(), out _);
    }

    private void OnNewRunPressed()
    {
        if (HasValidAutosave() && _overwriteConfirmDialog is not null)
        {
            _lastDialogFocusPreferenceForTest = "cancel";
            _overwriteConfirmDialog.PopupCentered();
            CallDeferred(MethodName.FocusOverwriteCancelButton);

            return;
        }

        StartNewRun();
    }

    private void OnOverwriteConfirmed()
    {
        StartNewRun();
    }

    private void OnOverwriteCanceled()
    {
        // Cancel keeps autosave and menu state unchanged.
    }

    private void FocusOverwriteCancelButton()
    {
        if (_overwriteConfirmDialog?.GetCancelButton() is BaseButton cancelButton)
        {
            cancelButton.GrabFocus();
        }
    }

    private void StartNewRun()
    {
        Publish("ui.menu.new_run", "ui");
        Publish("ui.menu.start", "ui");
        Publish(EventTypes.RunStarted, "ui");
        HideMenu();
    }

    private void OnContinuePressed()
    {
        if (!HasValidAutosave())
        {
            Publish(EventTypes.RunContinueBlocked, "ui");
            RefreshContinueAvailability();
            return;
        }

        Publish("ui.menu.continue", "ui");
        Publish(EventTypes.RunResumed, "ui");
        HideMenu();
    }

    private void OnQuitPressed()
    {
        _quitRequested = true;
        Publish("ui.menu.quit", "ui");
        _quitIntentReachedForTest = true;
        if (_hasQuitRequestCallbackForTest)
        {
            _quitRequestCallbackForTest.Call();
            return;
        }

        if (!_disableQuitForTests)
        {
            GetTree().Quit();
        }
    }
}

