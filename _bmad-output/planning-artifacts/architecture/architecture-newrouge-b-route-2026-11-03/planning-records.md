# B 路线共享记录与提交合同

本文件是新架构的公共接口合同，细化主干 AD-3、5–11；所述新增记录尚待实施。实现通过单一受治理schema／codec和公共服务提供，不允许各消费者独立解释相同字段。既有 Taskmaster、MVG checkpoint、runtime receipt 格式继续由其 owning 模块管理；适配引用，不复制权威。

## 记录与写入归属

所有路径相对仓库。新版本化记录位于 `docs/planning/b-route/`，与派生 `semantic-topology` 分开。

| 记录 | 公共最小形状 | 唯一受管写者 |
| --- | --- | --- |
| `policy.v1.json` | `schema_version`、`policy_id`、`policy_revision`、切换边界、冻结A定义／来源清单引用 | 经审阅的迁移／策略适配 |
| `plans/<plan_id>/<revision>.json` | `schema_version`、`plan_id`、`revision`、`source_identity`、Requirement、Flow／非Flow去向、逻辑四部分／交接、适用性、采纳proof引用、lineage | 3B采纳协调器；修订不可变 |
| `bindings/<plan_id>/<binding_revision>.json` | `schema_version`、`binding_revision`、精确plan引用、stage、Task映射、四部分责任、契约／资源／测试义务、适用manifest或其他验证依据 | 3C／4／5适配通过同一提交服务；新修订不改旧plan |
| `task-origins.v1.json` | `schema_version`、每Task的B来源与完整适用plan集合、冻结legacy引用；无Task状态 | 三联编译／绑定提交的治理适配 |
| `commits/<operation_id>.json` | `schema_version`、操作内容身份、目标／authority前后digest、scope、plan／binding引用、正式目标结果摘要 | 共享apply服务；最小receipt纳入版本管理 |
| `catalog.v1.json` | `schema_version`、策略与origins引用、各scope已提交head／receipt、反向Task索引；不含Task状态或runtime通过结论 | 共享apply服务的单一最终发布点 |

schema标识分别使用 `newrouge.b-route-policy.v1`、`newrouge.b-route-plan.v1`、`newrouge.b-route-binding.v1`、`newrouge.b-route-origins.v1`、`newrouge.b-route-commit.v1`、`newrouge.b-route-catalog.v1`。同标识在所有producer／consumer中只有一个公共schema定义；字段类型、枚举及约束由该定义冻结，扩展经兼容性检查或升版，不允许同v1自由增加私有语义。

`plan_id` 为持久分配的非空字符串身份；`revision`／`binding_revision` 为各自单调正整数，路径用其无前导零十进制表示。binding必须分别记录所引plan的revision，不能用同一数字同时表示两类修订。一个Flow可在多个plan中被引用，但同一Flow的当前语义定义只由catalog中一个owner修订提供；其他plan引用该定义。跨Flow共享命令／状态也只有一个定义owner。重复／冲突owner阻断采纳。Task IDs 继续由现有任务分配与编译路径拥有，不由plan标题或模型文字派生；既有文件ID类型不改，内部引用由同一Taskmaster join适配解析。

commit receipt的目标digest不包含receipt自身或最终catalog的输出digest，避免自引用hash循环；catalog引用receipt及其digest。journal在receipt最终确定后保存catalog完整after payload／digest。receipt的operation内容身份及结果目标均不可变，审计事件不进入其内容身份。

初始schema／codec是后续消费者实现的前置共同产物，不要求前置规划先有运行时类或Godot节点。3B记录可完全没有Task映射；首次bootstrap可提交空Task origins／空冻结A集合，不能要求真实Task或Chapter5 witness才能初始化策略。来源审计／语义采纳按其阶段验证，只有Task消费才做Task路由分类。stage字段只表示已具备的定义层级，不是Task完成状态。4／5的planned对象引用允许尚未存在，但相关责任与以后检查必须明确。

## 引用、类型及内容身份

公共引用包含仓库相对POSIX `path`、明确 `schema_version`／实体ID／修订及带算法标签的digest。拒绝绝对路径、越出仓库的`..`、根外符号链接、未知实体和损坏引用。外部来源由既有source登记机制冻结，不把任意URL当本地文件。

JSON解析先拒绝重复键、非有限数、未知schema和错误类型，不将布尔当数字或字符串当ID类型。规范化codec沿项目 `canonical_sha` 约定：对象键序／JSON排版不影响语义digest，数组序、类型和值保留；不做隐式Unicode、字符串内容空白或集合排序转换。raw文件digest另存，冻结传输及历史proof仍按其原字节／版本验证。

一个 `InputSet` 由公共resolver构造，包含相关source／Ledger／Requirement、plan及binding修订、Task定义与Acceptance、契约／ADR／Overlay、适用manifest／其他验证、注册依赖闭包、检查规则／codec版本，以及影响结果的工具／环境身份。`input_set_digest` 对这些规范化条目计算；每条保原定位／raw身份及规范化策略。缺失或未知条目不能静默剔除。

Task定义投影只排除公共schema明确列举的可变状态／进度字段；Acceptance、依赖、来源、责任及验证义务不排除。不因其他Task状态或无关catalog条目变化重算全部语义；入口实时核对当前依赖／任务资格和源文件，不把旧缓存当资格证明。相关依赖未知时扩大适用闭包并阻断无法证明的新鲜度。

commit receipt对每个目标冻结 `verification_mode`、codec版本及投影digest：不可变plan／binding／receipt使用 `immutable_bytes`；Taskmaster及业务视图在后续消费时使用 `task_definition_projection`，原始before／after字节仍保作提交证明。初版可变allowlist仅Task和subtask的status，新增进度字段须先版本化定义，不能任意忽略字段。完成操作no-op允许合法状态推进，只复验相关定义和实时资格，不把旧after字节重新写回；未完成操作仍严格核对前像，状态并发冲突时先停止／重新派生，不覆盖。其他Task定义变化不影响本Task时，按各自规范化投影判断，而不比较整份tasks文件作为所有Task的新鲜度键。

## Task 来源分类和非 Flow

先验证策略、catalog、origins的已提交身份，再分类；不先看可选trace是否存在。判为A须匹配冻结Task ID、定义／来源scope、允许的旧路线操作，且完整反向索引没有当前B义务。任何新增或相关定义变化按B规则承接；B origins追加／迁移不可被删除降回A。缺任一必需治理记录即阻断，不推断“系统尚未使用B”。迁移启用前仅沿显式原入口运行旧范围，启用后全部入口都使用统一分类。

按Task计算的plan集合须与plan／binding中的反向引用完全一致；apply时检查完整映射，不让缺行被当作无义务。Task进入新plan的变更会改变其适用集合／InputSet，已有A资格或readiness不能遮蔽。对origins、索引或策略的直接文件改动会使已发布receipt/hash不匹配，不能作为合法豁免。

3B采纳去向对每Requirement解释 `flow`、`other_verification`、有依据延期或来源缺口；沿现有唯一权威verification及route／evidence键。Task的 `mvg_required` 由有效定义和实际传递影响推导，不能由Agent自由填写。非Flow且无MVG责任仍须有效已采纳理由和其他验证；若影响已有Flow，追加对应manifest／回归绑定。Flow中的纯集成owner只承接其测试角色，不凭owner身份制造业务API或自身done前置。

## 共享 apply 与恢复协议

1. **prepare／preview：** 对冻结输入、目标before身份、完整Task join、旧状态保留、累计delta／防削弱和受影响scope做机器及必要语义审阅。持久绑定operation ID与规范化请求内容；同ID异内容冲突。重试使用同请求及分配结果，不再次生成身份。
2. **reserve：** 共享项目操作锁串行化所有受管规划／编译／绑定写者，沿现有服务锁与必要跨进程锁，不新建第二套互不知晓的锁。登记持久pending及完整journal；源authority／目标before／after／payload须在写前完整验证。目标编辑／占用不满足写入条件则停，不强制覆盖。
3. **apply：** 每个目标只接受原before或本操作after身份，写前复核；已after者跳过。Taskmaster可变状态在同一锁内从当前权威合并，若和journal前像冲突则停止／重新审阅派生delta，不以宽泛mutable排除吞掉Acceptance或新进度。
4. **verify：** 重读所有目标、当前authority及适用映射，验证新InputSet、三联／manifest一致性；持久保存最小不可变commit receipt，完整payload及过程证据留logs。写receipt或单个文件不等于发布完成。
5. **publish：** 只有上步全部通过，才最后原子替换 `catalog.v1.json`，一次推进本操作涉及的全部scope，并保留无关scope。它是本服务正式可见性的唯一发布点；MVG自己的 `run.json` selected提交点继续由现有协调器拥有，两者不互相冒充。之后可清理本操作pending并写审计事件；事件不是提交点。
6. **recover：** 核对operation内容、journal／receipt、全authority和目标实际bytes，区分未写、已写未发布、已发布。已发布且身份匹配则no-op；有未知后编辑／损坏／同ID冲突则保留全部证据并停止，不盲重放、不覆盖、不重新付模型费用。pending消失或journal存在本身不能证明完成。

消费者在持有适用读／执行保护时读取catalog及所引用的receipt／InputSet，复核相关实际文件，再重读catalog；有冲突／漂移则重试或阻断。影响当前scope的pending在恢复消歧并清理前阻断，即便catalog可能已经发布。共享gate同时识别既有 `docs/planning/semantic-topology/capability-apply.pending.json` 及其原journal，按原apply恢复；不能只查新B pending。无法证明旧marker作用域时保守阻断适用规划／实施，catalog有效也不豁免，不删除marker获取通过。没有本地pending的clone也须验证提交链，不能因logs缺失就消费混合状态。无关scope发布不使当前Task语义失效，但若其实际依赖或适用集合变更则失效。

锁顺序由共享服务固定：先短时项目metadata锁，再按稳定scope ID顺序获取适用写／执行租约；获取不到则返回冲突，不持有全局锁等待长任务。运行可保留scope租约，但模型调用／任务执行期间不持有项目metadata锁；不相关scope仍可推进。读取snapshot后释放短锁，持scope保护在副作用边界重验。新增计划改变共享Task的适用集合时，提交涉及该Task当前和新增scope的完整租约集合。

所有受管写者遵守同一锁／提交服务，运行中的实施入口固定本次InputSet并在副作用／恢复边界重验；同scope的绑定替换不得与该执行租约并行推进。没有可取得的互斥保护时拒绝写入。人工目标编辑应在受管操作退出后进行；发现后编辑或Windows文件占用必须报冲突，不能宣称此协议提供针对任意不合作外部写者的数据库隔离保证。Windows单文件替换、flush和故障点由共享实现验证，未验证前不切默认B。

rollback不直接还原旧before文件覆盖后续编辑；使用新的受审阅补偿operation，确认当前前像、原副作用和适用边界，保旧历史／B来源与当前已完成Task状态。不得为重试而擦除原始journal／receipt。

既有MVG clear／epoch清理作用于本地生成结果的恢复、显示与发布资格，不自动删除版本化正式采纳或Git中的累计回归基线。正式采纳使用自身catalog／source／receipt有效性；引用旧checkpoint时保留其冻结proof，不能把失效的本地恢复资格伪装为当前新候选准入。source-backed正式语义变化仍须受治理地更新／失效相关采纳与绑定；local clear本身不等于该变更授权。

## 影响与执行范围接口

共享 `VerificationScope` 合同使用 `schema_version = newrouge.b-route-verification-scope.v1`、`scope_id`、`input_set_digest`、当前plan／manifest与累计基线、变更根、已计算传递影响及证明、三类义务、声明要执行的测试和人工责任。义务引用现有稳定Flow／test／Requirement身份；同一Flow可同时有既有和新增义务。

反向边来自已提交四部分定义、契约／绑定、测试责任与既有manifest，不以页面图或Task类型标签推断。缺边／未知关系扩大到适用累计范围，再按来源及交付计划分类；不按当前可运行状态缩减本次责任。没有其他可证明边界时，保守范围是当前适用累计manifest，未实现对象仍作为未来／本次未完责任分别列明。

执行器以此合同真实选择执行或明确采用更大保守集合；回执引用同一 `scope_id`／digest、当前formal manifest及整合snapshot，列出 `requested_tests`、`executed_tests`、`not_run`（原因）、`manual_obligations`、结果证据和覆盖。缺项、跳过、空报告或新增未完义务不作PASS；因本次变更而失败的旧测试不能改列为future。沿已有正式runtime receipt／inventory／snapshot的验证，不另造full-MVG证明。

共享测试去重键由当前已有测试身份、输入、验证语义、环境及同一整合snapshot组成；引用去重结果不共享可变测试状态。单Task局部可运行、单Flow收尾和累计full分别判断，integration-only owner的测试编排不增加自身实现完成条件。

## 诊断与实施接入

公共返回至少含 `reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`；阶段或实体不适用时显式null，不用空值当授权。reason_code区分必需治理缺失、未知版本、引用／身份损坏、输入过期、未发布／pending、冲突、预算和语义问题。错误与全部入口共用同一枚举定义，不能只在页面解释。

各阶段执行者向既有logs写带operation／run、scope、stage、attempt身份的观测；至少保留已观察active耗时、实际dispatch数量、复用来源／原因、重复测试／预热、返工返回阶段及终止原因。相同event身份去重；不可观察值显式unknown，不将预留、暂停墙钟或模型估算宣称为实测成本／账单。记录不新建Task完成状态、速度门槛或分析平台。

接入范围包含来源／Ledger／独立审计、Capability／MVG planner、业务视图及三联compiler、Chapter4／5、`_mvg_obligations`及Chapter6 direct／route／resume、Chapter7、manifest校验／runner／milestone handoff、Knowledge／规划页、CLI／Skill／文档／示例和测试。旧 `_mvg_obligations` 的无trace返回current只能在统一分类确认的合法legacy边界内使用，不能先返回再补检查。

每个适配在共享服务下承接原公共入口，不预设3A／3B／3C各有新CLI。公共schema／codec／读写服务是后续消费者任务共同前置；具体模块拆分不是让消费者自行选择格式的许可。新增默认路径启用前须有切断绑定、删origin／manifest、损坏journal、发布前后崩溃、后编辑、跨scope共享Task、状态并发、epoch／reopen、合法非Flow及owner自依赖反例。
