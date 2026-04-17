using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Offers;
using Xunit;

namespace Game.Core.Tests.Repositories;

public class OfferProvenanceRepositoryTests
{
    // ACC:T46.7
    [Fact]
    public async Task ShouldPersistRngStreamAndGenerationBatch_WhenReloadedAndQueriedByContext()
    {
        var offerContextId = "ctx.task46.provenance.persisted";
        var expectedRngStream = "reward.offer";
        var expectedGenerationBatch = 42L;
        var provenance = CreateProvenance(expectedRngStream, expectedGenerationBatch);

        var repository = OfferProvenanceRepositoryHarness.Create();
        await repository.SaveAsync(offerContextId, provenance);

        var reloadedRepository = repository.CreateReloaded();
        var queriedProvenance = await reloadedRepository.GetAsync(offerContextId);

        queriedProvenance.Should().NotBeNull("provenance must be persisted and queryable after repository reload");
        queriedProvenance!.RngStream.Should().Be(expectedRngStream,
            "rng stream identifier is required for deterministic consistency checks");
        queriedProvenance.StreamPosition.Should().Be(expectedGenerationBatch,
            "generation batch must be preserved to support deterministic replay");
    }

    [Fact]
    public async Task ShouldReturnNullAndKeepExistingRecordUnchanged_WhenQueryingMissingContext()
    {
        var persistedContextId = "ctx.task46.provenance.existing";
        var missingContextId = "ctx.task46.provenance.missing";
        var persistedProvenance = CreateProvenance("reward.offer", 99L);

        var repository = OfferProvenanceRepositoryHarness.Create();
        await repository.SaveAsync(persistedContextId, persistedProvenance);

        var missingResult = await repository.GetAsync(missingContextId);
        var existingResult = await repository.GetAsync(persistedContextId);

        missingResult.Should().BeNull("querying an unknown context must not fabricate provenance data");
        existingResult.Should().NotBeNull("known context must remain queryable");
        existingResult!.RngStream.Should().Be("reward.offer");
        existingResult.StreamPosition.Should().Be(99L);
    }

    private static OfferProvenance CreateProvenance(string rngStream, long generationBatch)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.46",
            Act: 2,
            Floor: 11,
            NodeId: "N-2-11",
            Difficulty: 3,
            RngStream: rngStream,
            StreamPosition: generationBatch);
    }

    private sealed class OfferProvenanceRepositoryHarness
    {
        private static readonly string[] SaveMethodNames = { "SaveAsync", "UpsertAsync", "SetAsync", "PutAsync", "StoreAsync" };
        private static readonly string[] GetMethodNames = { "GetAsync", "LoadAsync", "FindAsync", "TryGetAsync", "ReadAsync" };

        private readonly Type repositoryType;
        private readonly object repositoryInstance;
        private readonly ConstructorInfo constructor;
        private readonly object?[] constructorArguments;
        private readonly MethodInfo saveMethod;
        private readonly MethodInfo getMethod;

        private OfferProvenanceRepositoryHarness(
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

        public static OfferProvenanceRepositoryHarness Create()
        {
            var repositoryTypes = AppDomain.CurrentDomain
                .GetAssemblies()
                .SelectMany(GetLoadableTypes)
                .Where(type => type is { IsInterface: false, IsAbstract: false })
                .Where(type => type.Assembly == typeof(OfferProvenance).Assembly)
                .Where(type => type.Name.Contains("OfferProvenanceRepository", StringComparison.OrdinalIgnoreCase))
                .ToArray();

            repositoryTypes.Should().ContainSingle(
                "Task 46 requires one concrete repository to persist and query offer provenance");

            var repositoryType = repositoryTypes[0];
            var storageRoot = Path.Combine(Path.GetTempPath(), "newrouge-task46", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(storageRoot);

            var binding = CreateConstructorBinding(repositoryType, storageRoot);
            var repositoryInstance = binding.Constructor.Invoke(binding.Arguments);

            repositoryInstance.Should().NotBeNull(
                "the offer provenance repository must be constructible for persistence tests");

            var saveMethod = FindSaveMethod(repositoryType);
            saveMethod.Should().NotBeNull(
                "repository must expose a save/upsert method for OfferProvenance");

            var getMethod = FindGetMethod(repositoryType);
            getMethod.Should().NotBeNull(
                "repository must expose a get/load method returning OfferProvenance");

            return new OfferProvenanceRepositoryHarness(
                repositoryType,
                repositoryInstance!,
                binding.Constructor,
                binding.Arguments,
                saveMethod!,
                getMethod!);
        }

        public OfferProvenanceRepositoryHarness CreateReloaded()
        {
            var copiedArguments = constructorArguments.ToArray();
            var reloadedInstance = constructor.Invoke(copiedArguments);

            reloadedInstance.Should().NotBeNull(
                "repository must be reconstructible to validate persisted state across reload");

            return new OfferProvenanceRepositoryHarness(
                repositoryType,
                reloadedInstance!,
                constructor,
                copiedArguments,
                saveMethod,
                getMethod);
        }

        public async Task SaveAsync(string offerContextId, OfferProvenance provenance)
        {
            var arguments = BuildInvocationArguments(saveMethod, offerContextId, provenance);
            var returnValue = saveMethod.Invoke(repositoryInstance, arguments);
            await AwaitIfNeededAsync(returnValue);
        }

        public async Task<OfferProvenance?> GetAsync(string offerContextId)
        {
            var arguments = BuildInvocationArguments(getMethod, offerContextId, provenance: null);
            var returnValue = getMethod.Invoke(repositoryInstance, arguments);
            var resolved = await AwaitIfNeededAsync(returnValue);

            if (resolved is null)
            {
                return null;
            }

            resolved.Should().BeOfType<OfferProvenance>(
                "repository get/load method must resolve to OfferProvenance or null");

            return (OfferProvenance)resolved;
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
                argument = new FileInfo(Path.Combine(storageRoot, "offer-provenance.json"));
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
                .Where(method => method.GetParameters().Any(parameter => parameter.ParameterType == typeof(OfferProvenance)))
                .OrderBy(method => method.GetParameters().Length)
                .FirstOrDefault();
        }

        private static MethodInfo? FindGetMethod(Type repositoryType)
        {
            return repositoryType
                .GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(method => GetMethodNames.Contains(method.Name, StringComparer.Ordinal))
                .Where(method => method.GetParameters().Any(parameter => parameter.ParameterType == typeof(string)))
                .Where(method => CanResolveOfferProvenance(method.ReturnType))
                .OrderBy(method => method.GetParameters().Length)
                .FirstOrDefault();
        }

        private static bool CanResolveOfferProvenance(Type returnType)
        {
            if (returnType == typeof(OfferProvenance))
            {
                return true;
            }

            if (typeof(Task).IsAssignableFrom(returnType) && returnType.IsGenericType)
            {
                return returnType.GetGenericArguments()[0] == typeof(OfferProvenance);
            }

            if (returnType.IsGenericType && returnType.GetGenericTypeDefinition() == typeof(ValueTask<>))
            {
                return returnType.GetGenericArguments()[0] == typeof(OfferProvenance);
            }

            return false;
        }

        private static object?[] BuildInvocationArguments(
            MethodInfo method,
            string offerContextId,
            OfferProvenance? provenance)
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

                if (parameter.ParameterType == typeof(OfferProvenance))
                {
                    arguments[index] = provenance;
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
