using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Repositories;

public class OfferLockRepositoryTests
{
    // ACC:T46.5
    [Fact]
    public async Task ShouldPersistStableIdsAndDisplayOrder_WhenReloadedWithSameInputAndSameRngStream()
    {
        var offerContextId = "ctx.task46.persisted";
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 128L);

        var firstService = new DeterministicOfferService();
        var firstSnapshot = firstService.LockOffer(offerContextId, candidates, provenance);

        var repository = OfferLockRepositoryHarness.Create();
        await repository.SaveAsync(offerContextId, firstSnapshot);

        var reloadedRepository = repository.CreateReloaded();
        var reloadedSnapshot = await reloadedRepository.GetAsync(offerContextId);

        reloadedSnapshot.Should().NotBeNull("offer lock snapshots must survive repository reload");
        reloadedSnapshot!.StableIds.Should().Equal(firstSnapshot.StableIds);
        reloadedSnapshot.DisplayOrder.Should().Equal(firstSnapshot.DisplayOrder);

        var reloadedService = new DeterministicOfferService();
        var regeneratedSnapshot = reloadedService.LockOffer("ctx.task46.regenerated", candidates, provenance);

        regeneratedSnapshot.StableIds.Should().Equal(reloadedSnapshot.StableIds,
            "same input and same RNG stream must regenerate the same stable_id set");
        regeneratedSnapshot.DisplayOrder.Should().Equal(reloadedSnapshot.DisplayOrder,
            "same input and same RNG stream must regenerate the same display_order");
    }

    [Fact]
    public async Task ShouldReturnNull_WhenOfferContextIdWasNotPersisted()
    {
        var persistedContextId = "ctx.task46.persisted";
        var missingContextId = "ctx.task46.missing";
        var candidates = CreateCandidates("offer.alpha", "offer.beta");
        var provenance = CreateProvenance("reward.offer", 256L);

        var service = new DeterministicOfferService();
        var persistedSnapshot = service.LockOffer(persistedContextId, candidates, provenance);

        var repository = OfferLockRepositoryHarness.Create();
        await repository.SaveAsync(persistedContextId, persistedSnapshot);

        var reloadedRepository = repository.CreateReloaded();
        var missingSnapshot = await reloadedRepository.GetAsync(missingContextId);

        missingSnapshot.Should().BeNull("repository must not return a lock snapshot for an unknown context id");
    }

    private static IReadOnlyList<OfferItem> CreateCandidates(params string[] offerItemIds)
    {
        return offerItemIds
            .Select((offerItemId, index) => new OfferItem(
                OfferItemId: offerItemId,
                CardId: $"card.{offerItemId}",
                Form: index % 2 == 0 ? CardForm.Base : CardForm.U1A,
                Route: index % 2 == 0 ? null : UpgradeRoute.A,
                Rarity: index % 2 == 0 ? "common" : "rare"))
            .ToArray();
    }

    private static OfferProvenance CreateProvenance(string rngStream, long streamPosition)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.46",
            Act: 2,
            Floor: 9,
            NodeId: "N-2-9",
            Difficulty: 3,
            RngStream: rngStream,
            StreamPosition: streamPosition);
    }

    private sealed class OfferLockRepositoryHarness
    {
        private static readonly string[] SaveMethodNames = { "SaveAsync", "UpsertAsync", "SetAsync", "PutAsync", "StoreAsync" };
        private static readonly string[] GetMethodNames = { "GetAsync", "LoadAsync", "FindAsync", "TryGetAsync", "ReadAsync" };

        private readonly Type repositoryType;
        private readonly object repositoryInstance;
        private readonly ConstructorInfo constructor;
        private readonly object?[] constructorArguments;
        private readonly MethodInfo saveMethod;
        private readonly MethodInfo getMethod;

        private OfferLockRepositoryHarness(
            Type repositoryType,
            object repositoryInstance,
            ConstructorInfo constructor,
            object?[] constructorArguments,
            MethodInfo saveMethod,
            MethodInfo getMethod)
        {
            this.repositoryType = repositoryType;
            this.repositoryInstance = repositoryInstance;
            this.constructor = constructor;
            this.constructorArguments = constructorArguments;
            this.saveMethod = saveMethod;
            this.getMethod = getMethod;
        }

        public static OfferLockRepositoryHarness Create()
        {
            var repositoryTypes = AppDomain.CurrentDomain
                .GetAssemblies()
                .SelectMany(GetLoadableTypes)
                .Where(type => type is { IsInterface: false, IsAbstract: false })
                .Where(type => type.Assembly == typeof(OfferLockSnapshot).Assembly)
                .Where(type => type.Name.Contains("OfferLockRepository", StringComparison.OrdinalIgnoreCase))
                .ToArray();

            repositoryTypes.Should().ContainSingle(
                "Task 46 requires one concrete repository to persist offer lock snapshots");

            var repositoryType = repositoryTypes[0];
            var storageRoot = Path.Combine(Path.GetTempPath(), "newrouge-task46", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(storageRoot);

            var binding = CreateConstructorBinding(repositoryType, storageRoot);
            var repositoryInstance = binding.Constructor.Invoke(binding.Arguments);

            repositoryInstance.Should().NotBeNull(
                "the offer lock repository must be constructible for persistence tests");

            var saveMethod = FindSaveMethod(repositoryType);
            saveMethod.Should().NotBeNull(
                "repository must expose a save/upsert method for OfferLockSnapshot");

            var getMethod = FindGetMethod(repositoryType);
            getMethod.Should().NotBeNull(
                "repository must expose a get/load method returning OfferLockSnapshot");

            return new OfferLockRepositoryHarness(
                repositoryType,
                repositoryInstance!,
                binding.Constructor,
                binding.Arguments,
                saveMethod!,
                getMethod!);
        }

        public OfferLockRepositoryHarness CreateReloaded()
        {
            var copiedArguments = constructorArguments.ToArray();
            var reloadedInstance = constructor.Invoke(copiedArguments);

            reloadedInstance.Should().NotBeNull(
                "repository must be reconstructible to validate persisted state across reload");

            return new OfferLockRepositoryHarness(
                repositoryType,
                reloadedInstance!,
                constructor,
                copiedArguments,
                saveMethod,
                getMethod);
        }

        public async Task SaveAsync(string offerContextId, OfferLockSnapshot snapshot)
        {
            var arguments = BuildInvocationArguments(saveMethod, offerContextId, snapshot);
            var returnValue = saveMethod.Invoke(repositoryInstance, arguments);
            await AwaitIfNeededAsync(returnValue);
        }

        public async Task<OfferLockSnapshot?> GetAsync(string offerContextId)
        {
            var arguments = BuildInvocationArguments(getMethod, offerContextId, snapshot: null);
            var returnValue = getMethod.Invoke(repositoryInstance, arguments);
            var resolved = await AwaitIfNeededAsync(returnValue);

            if (resolved is null)
            {
                return null;
            }

            resolved.Should().BeOfType<OfferLockSnapshot>(
                "repository get/load method must resolve to OfferLockSnapshot or null");

            return (OfferLockSnapshot)resolved;
        }

        private static ConstructorBinding CreateConstructorBinding(Type repositoryType, string storageRoot)
        {
            var constructors = repositoryType
                .GetConstructors(BindingFlags.Public | BindingFlags.Instance)
                .OrderBy(constructor => constructor.GetParameters().Length)
                .ToArray();

            foreach (var constructor in constructors)
            {
                if (TryCreateConstructorArguments(constructor, storageRoot, out var arguments))
                {
                    return new ConstructorBinding(constructor, arguments);
                }
            }

            throw new InvalidOperationException(
                $"Unable to construct {repositoryType.FullName} with supported deterministic test arguments.");
        }

        private static bool TryCreateConstructorArguments(
            ConstructorInfo constructor,
            string storageRoot,
            out object?[] arguments)
        {
            var parameters = constructor.GetParameters();
            arguments = new object?[parameters.Length];

            for (var index = 0; index < parameters.Length; index++)
            {
                if (!TryResolveConstructorArgument(parameters[index], storageRoot, out var argument))
                {
                    return false;
                }

                arguments[index] = argument;
            }

            return true;
        }

        private static bool TryResolveConstructorArgument(
            ParameterInfo parameter,
            string storageRoot,
            out object? argument)
        {
            if (parameter.HasDefaultValue)
            {
                argument = parameter.DefaultValue;
                return true;
            }

            if (parameter.ParameterType == typeof(string))
            {
                argument = storageRoot;
                return true;
            }

            if (parameter.ParameterType == typeof(DirectoryInfo))
            {
                argument = new DirectoryInfo(storageRoot);
                return true;
            }

            if (parameter.ParameterType == typeof(FileInfo))
            {
                argument = new FileInfo(Path.Combine(storageRoot, "offer-locks.json"));
                return true;
            }

            if (parameter.ParameterType == typeof(CancellationToken))
            {
                argument = CancellationToken.None;
                return true;
            }

            if (parameter.ParameterType.IsValueType)
            {
                argument = Activator.CreateInstance(parameter.ParameterType);
                return true;
            }

            if (parameter.ParameterType.GetConstructor(Type.EmptyTypes) is not null)
            {
                argument = Activator.CreateInstance(parameter.ParameterType);
                return true;
            }

            argument = null;
            return false;
        }

        private static MethodInfo? FindSaveMethod(Type repositoryType)
        {
            return repositoryType
                .GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(method => SaveMethodNames.Contains(method.Name, StringComparer.Ordinal))
                .Where(method => method.GetParameters().Any(parameter => parameter.ParameterType == typeof(string)))
                .Where(method => method.GetParameters().Any(parameter => parameter.ParameterType == typeof(OfferLockSnapshot)))
                .OrderBy(method => method.GetParameters().Length)
                .FirstOrDefault();
        }

        private static MethodInfo? FindGetMethod(Type repositoryType)
        {
            return repositoryType
                .GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(method => GetMethodNames.Contains(method.Name, StringComparer.Ordinal))
                .Where(method => method.GetParameters().Any(parameter => parameter.ParameterType == typeof(string)))
                .Where(method => CanResolveOfferLockSnapshot(method.ReturnType))
                .OrderBy(method => method.GetParameters().Length)
                .FirstOrDefault();
        }

        private static bool CanResolveOfferLockSnapshot(Type returnType)
        {
            if (returnType == typeof(OfferLockSnapshot))
            {
                return true;
            }

            if (typeof(Task).IsAssignableFrom(returnType) && returnType.IsGenericType)
            {
                return returnType.GetGenericArguments()[0] == typeof(OfferLockSnapshot);
            }

            if (returnType.IsGenericType && returnType.GetGenericTypeDefinition() == typeof(ValueTask<>))
            {
                return returnType.GetGenericArguments()[0] == typeof(OfferLockSnapshot);
            }

            return false;
        }

        private static object?[] BuildInvocationArguments(
            MethodInfo method,
            string offerContextId,
            OfferLockSnapshot? snapshot)
        {
            var parameters = method.GetParameters();
            var arguments = new object?[parameters.Length];

            for (var index = 0; index < parameters.Length; index++)
            {
                var parameter = parameters[index];

                if (parameter.ParameterType == typeof(string))
                {
                    arguments[index] = offerContextId;
                    continue;
                }

                if (parameter.ParameterType == typeof(OfferLockSnapshot))
                {
                    arguments[index] = snapshot;
                    continue;
                }

                if (parameter.ParameterType == typeof(CancellationToken))
                {
                    arguments[index] = CancellationToken.None;
                    continue;
                }

                if (parameter.HasDefaultValue)
                {
                    arguments[index] = parameter.DefaultValue;
                    continue;
                }

                arguments[index] = parameter.ParameterType.IsValueType
                    ? Activator.CreateInstance(parameter.ParameterType)
                    : null;
            }

            return arguments;
        }

        private static async Task<object?> AwaitIfNeededAsync(object? value)
        {
            if (value is null)
            {
                return null;
            }

            if (value is Task task)
            {
                await task.ConfigureAwait(false);
                return task.GetType().IsGenericType
                    ? task.GetType().GetProperty("Result")?.GetValue(task)
                    : null;
            }

            var valueType = value.GetType();
            if (valueType.IsGenericType && valueType.GetGenericTypeDefinition() == typeof(ValueTask<>))
            {
                var asTaskMethod = valueType.GetMethod("AsTask", Type.EmptyTypes);
                var asTask = asTaskMethod?.Invoke(value, null) as Task;
                asTask.Should().NotBeNull("ValueTask<T> should be convertible to Task<T> for test awaiting");

                await asTask!.ConfigureAwait(false);
                return asTask.GetType().GetProperty("Result")?.GetValue(asTask);
            }

            if (valueType == typeof(ValueTask))
            {
                var asTaskMethod = valueType.GetMethod("AsTask", Type.EmptyTypes);
                var asTask = asTaskMethod?.Invoke(value, null) as Task;
                asTask.Should().NotBeNull("ValueTask should be convertible to Task for test awaiting");

                await asTask!.ConfigureAwait(false);
                return null;
            }

            return value;
        }

        private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
        {
            try
            {
                return assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException ex)
            {
                return ex.Types
                    .Where(type => type is not null)
                    .Select(type => type!);
            }
        }

        private sealed record ConstructorBinding(ConstructorInfo Constructor, object?[] Arguments);
    }
}
