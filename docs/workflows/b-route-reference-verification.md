# B 路线只读内容与引用核验

Story 1.3 提供 [`_b_route_codec.py`](../../scripts/python/_b_route_codec.py) 和独立入口 [`verify_b_route_reference.py`](../../scripts/python/verify_b_route_reference.py)。两者共用严格 JSON、类型化引用、身份 registry、codec 版本和诊断定义。

`content` 检查严格 JSON、已知 schema 和当前可证明的实体身份，并计算内容 digest；`reference` 还检查完整引用、仓库内路径及目标的 schema、实体、修订和所选 digest。成功仅证明本次读取的内容或引用身份。输出始终含 `schema_validated: false`，不授予完整记录合规、规划采纳、Task 准入、提交／发布成功或运行验收结论。六类完整 schema 属于 Story 1.4；journal、InputSet、默认 B 切换和 A 退出不在此入口范围内。

## 公共 API

调用方将 `scripts/python` 加入 Python 模块搜索路径后，从 `_b_route_codec` 导入公共定义。命令推荐使用 `py -3 -B`；CLI 自身也会在导入公共模块前禁用 bytecode 写入。

| API | 输入与结果 |
| --- | --- |
| `strict_json_loads(data)` | 接受 UTF-8 `bytes` 或 JSON 文本 `str`，返回 JSON 值。拒绝非法 UTF-8、重复键、非法语法、NaN／Infinity／指数溢出和无效 Unicode 字符。 |
| `validate_json_value(value)` | 检查内存 JSON 树；拒绝非字符串对象键、非 JSON 类型、非有限数和循环引用。成功返回 `None`。 |
| `raw_digest(data)` | 接受原始 `bytes`，返回带 `sha256:` 标签的字节 digest，不转换换行或编码。 |
| `canonical_digest(value, codec_version=CODEC_VERSION)` | 严格检查内存 JSON 后，沿用原 `canonical_sha` 算法计算 digest；未知 codec 版本拒绝。 |
| `validate_task_id(value)` | 接受严格正整数；拒绝 `bool`、字符串和浮点数，不做类型转换。适用于现有 master ID／`taskmaster_id` 类型。 |
| `validate_business_id(value)` | 保留业务视图自己的非空、无首尾空白字符串 ID；不转换为 master ID。 |
| `validate_reference_path(path)` | 只做仓库相对 POSIX 路径词法检查，不证明文件存在或实际 containment。 |
| `resolve_reference_path(root, path)` | 按实际文件系统逐段解析并核对 containment；返回可证明位于根内的 `Path`。 |
| `read_reference_bytes(root, path)` | 只读根内普通文件，核对读取前后已观察的文件身份，返回 `bytes`。 |
| `TypedReference.from_value(value)` | 从完整引用对象构造不可变引用；缺字段、额外字段、错误类型、坏模式／版本／digest 均拒绝。 |
| `verify_content(data)` | 接受 JSON 字节、文本或内存对象，返回 `VerificationResult`。内存对象没有原始文件字节，因此 `raw_digest` 为 `null`。 |
| `verify_content_file(root, path)` | 只读仓库相对文件，返回 content 结果。 |
| `verify_reference(root, reference)` | 接受 `TypedReference`、完整引用对象、JSON 字节或文本，返回 reference 结果。 |

低层检查失败抛出 `CodecError`，其 `diagnostic` 使用同一 `Diagnostic` 类型；`verify_*` 将已识别的核验失败转为 `ok: false` 结果。`VerificationResult.to_dict()` 输出可序列化对象，包含 `verification_kind`、`claim`、`target_verified`、`schema_validated`、`diagnostic`、`content_identity`、已证明的实体／修订及 `path`。文件或引用结果的 `path` 定位原输入路径；内存内容或无法取得路径时为 `null`。仅 reference 成功时 `target_verified` 为 `true`；content 成功仍为 `false`。

`ContentIdentity` 分别保存 `raw_digest`、`canonical_digest` 和 `codec_version`。当前版本常量为 `newrouge.b-route-json.v1`，算法继续使用 `ensure_ascii=False`、对象键排序和紧凑分隔符。对象键顺序与 JSON 排版变化不改变 canonical digest；数组顺序、JSON 类型、Unicode 原值和字符串内容空白均保留差异。不做 Unicode 规范化、集合排序或字符串裁剪。旧 `canonical_sha`、原始 proof 字节和原 codec 版本不因新核验结果而改写。

## 唯一身份 registry 与引用形状

`SCHEMA_IDENTITY_REGISTRY` 是公共模块内唯一、只读的 schema 身份 owner。当前登记六类记录的 `newrouge.b-route-{policy,plan,binding,origins,commit,catalog}.v1`，以及 `newrouge.b-route-verification-scope.v1`。只有 `newrouge.b-route-plan.v1` 已有足够合同支持 adapter：`plan_id` 为非空原字符串，`revision` 为严格正整数。仅检查顶层记录／引用的 schema，不拒绝扩展对象内部同名的 `schema_version` 键。

其他已知 schema 缺少经定义的实体／修订 adapter 时返回 `identity_unprovable`，不推断文件名、`v1`、digest 或缺失字段的含义，也不报告通过。未知 schema 返回 `unknown_schema`；引用与目标的已知 schema 不符返回 `schema_mismatch`；目标 plan ID 与引用不符返回 `unknown_entity`；修订与 digest 差异分别返回 `revision_mismatch`、`digest_mismatch`。Story 1.4 必须扩展同一 registry；消费者与 CLI 不自行配置字段映射或私设相同 schema 的解释。

类型化引用是只读输入类型，不是新增正式规划记录。以下七个字段都必须显式提供，不能靠默认值补齐身份：

| 字段 | 合同 |
| --- | --- |
| `path` | 仓库根相对 POSIX 路径，使用 `/`。 |
| `schema_version` | registry 中的明确目标 schema 标识。 |
| `entity_id` | 引用声称的非空字符串实体身份。 |
| `revision` | 引用声称的严格正整数修订；`true`、`"1"`、`1.0` 均拒绝。 |
| `digest` | `sha256:` 后接 64 位小写十六进制字符。 |
| `verification_mode` | 明确为 `raw` 或 `canonical`。此处不是后续 receipt 的投影策略枚举。 |
| `codec_version` | canonical 模式必须明确为 `newrouge.b-route-json.v1`；raw 模式必须显式为 `null`。 |

raw 模式核对原字节 digest；canonical 模式核对按指定 codec 得到的语义 digest。两种模式都严格解析目标 JSON 并核对实体身份，不能以字节命中绕过损坏内容或缺 adapter。成功结果同时返回两种 digest，不静默替换引用选择。

路径检查拒绝绝对路径、驱动器路径、UNC、反斜杠、URL、ADS、Windows 设备／别名路径及根逃逸。合法的 `sub/../plan.json` 和可证明目标位于根内的 symlink／junction 允许通过；根外链接拒绝，无法解析或证明 containment 则失败。外部来源仍由既有 source 登记与冻结机制管理。读取失败、非普通文件或已观察的读取漂移也返回公共诊断。读取前后检查不构成针对任意并发外部写者的事务隔离保证。

## Windows 命令与隔离示例

从仓库根执行：

```powershell
py -3 -B scripts/python/verify_b_route_reference.py content --repo-root . --path logs/ci/example/plan.json
py -3 -B scripts/python/verify_b_route_reference.py reference --repo-root . --reference logs/ci/example/reference.json
py -3 -B -m unittest discover -s scripts/python/tests -p test_b_route_codec.py -v
```

CLI 正常核验时 stdout 为一个英文 JSON 对象，成功退出码为 `0`，失败为非零；参数错误同样使用公共诊断。若参数错误仍可识别 `content`／`reference` 模式，结果保留对应模式；无法识别模式时 `verification_kind`、`claim` 和诊断 `stage` 为 `null`。`--help` 显示英文命令帮助。CLI 只读输入，不创建日志、`__pycache__`、正式规划文件、Task 三联或发布指针，没有写入／发布选项，也不调用 Godot、模型或数据库。日志文件由调用者保存到本轮新建的 `logs/**` 目录。

下面的 PowerShell 示例只在一个全新的 logs 目录中准备示例和保存输出。示例 plan 仅用于身份核验，不是完整合法或已采纳的正式 plan。

```powershell
$repoRoot = (Get-Location).Path
$fixtureRel = "logs/ci/$(Get-Date -Format yyyy-MM-dd)/b-route-codec-example-$([Guid]::NewGuid().ToString('N'))"
$fixtureDir = Join-Path $repoRoot $fixtureRel
New-Item -ItemType Directory -Path $fixtureDir -ErrorAction Stop | Out-Null

$fixtureScript = @'
import json
import sys
from pathlib import Path

root, relative = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(root / "scripts/python"))
from _b_route_codec import CODEC_VERSION, PLAN_SCHEMA, canonical_digest, raw_digest

folder = root / relative
record = {"schema_version": PLAN_SCHEMA, "plan_id": "example-plan", "revision": 1}
data = (json.dumps(record, indent=2) + "\n").encode("utf-8")
(folder / "plan.json").write_bytes(data)
reference = {
    "path": relative + "/plan.json",
    "schema_version": PLAN_SCHEMA,
    "entity_id": "example-plan",
    "revision": 1,
    "digest": canonical_digest(record),
    "verification_mode": "canonical",
    "codec_version": CODEC_VERSION,
}
def save(name, value):
    (folder / name).write_bytes((json.dumps(value, indent=2) + "\n").encode("utf-8"))
save("reference.json", reference)
save("reference-raw.json", dict(reference, digest=raw_digest(data), verification_mode="raw", codec_version=None))
save("reference-bad.json", dict(reference, digest="sha256:" + "0" * 64))
'@
$fixtureScript | py -3 -B - $repoRoot $fixtureRel
if ($LASTEXITCODE -ne 0) { throw "Fixture preparation failed" }

$utf8 = [System.Text.UTF8Encoding]::new($false)
$contentOutput = & py -3 -B scripts/python/verify_b_route_reference.py content --repo-root $repoRoot --path "$fixtureRel/plan.json"
$contentExit = $LASTEXITCODE
[System.IO.File]::WriteAllText((Join-Path $fixtureDir "content.stdout.json"), (($contentOutput -join "`n") + "`n"), $utf8)
if ($contentExit -ne 0) { throw "Content example failed" }

foreach ($name in @("reference", "reference-raw", "reference-bad")) {
    $output = & py -3 -B scripts/python/verify_b_route_reference.py reference --repo-root $repoRoot --reference "$fixtureRel/$name.json"
    $exitCode = $LASTEXITCODE
    [System.IO.File]::WriteAllText((Join-Path $fixtureDir "$name.stdout.json"), (($output -join "`n") + "`n"), $utf8)
    [System.IO.File]::WriteAllText((Join-Path $fixtureDir "$name.exit.txt"), "$exitCode`n", $utf8)
    if ($name -eq "reference-bad") {
        if ($exitCode -eq 0) { throw "Negative example unexpectedly passed" }
    } elseif ($exitCode -ne 0) {
        throw "Reference example failed"
    }
}
```

## 公共诊断与验证边界

`ReasonCode`、`Stage`、`Diagnostic` 由公共模块唯一拥有。每个诊断都序列化以下六个字段：`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`。不适用值显式为 `null`；本只读入口不创建恢复对象，因此没有可用恢复引用时 `resume_ref` 为 `null`。`stage` 描述 `decode`／`content`／`reference`／`path`／`target` 核验位置，不授予 B 路线阶段资格。空值不表示授权或通过。

诊断区分解析损坏、错误类型、未知 schema／codec、引用损坏、无法证明身份、未知实体、实际修订／digest 差异、路径问题、读取失败和漂移。错误输出不打印输入正文或异常中的文件内容。完整记录字段、历史 proof、Taskmaster join、正式采纳链和实时 Task 资格仍须由各自 owner 按原合同验证。

本轮 Linux 可验证严格 JSON、canonical 黄金值、Windows 路径词法及 Linux 上的根内／根外 symlink 行为。这些证据不能证明 Windows 实际文件 I/O、junction、大小写行为或文件占用处理。真实 Windows 环境应运行同一定向 unittest 与 CLI 正负例，并分别保存平台信息、实际输出和未运行／跳过原因；未取得这些原始证据前，Windows 平台验收保持未完成。不能以旧 Story 的 Windows 报告或 Linux 模拟代替本 Story 的平台验收。

每次定向验证预算为 180 秒，原始 stdout／stderr 和退出码保存在新 logs。核验工作还须对照 spec 矩阵、变更白名单与既有七个 dirty 文件 SHA，确认三联、游戏、旧 proof 和原 canonical 实现的字节未被改写；本说明本身不声称这些检查已经完成。
