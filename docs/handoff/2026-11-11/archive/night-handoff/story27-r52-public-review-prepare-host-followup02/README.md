# Followup02 — HOLD，精确封存空目录修复

本包冻结保存控制修复，**当前不请求Root执行**。Root将先在同一真实r52路径集成已审common+journal正式路径修复和单一新test，形成新commit/tests/exactdelta bridge，再重新真实采集protection/verify、builder及Request02。本02仍绑定旧source885/旧protection/d44历史，不会被签成那个新epoch。完整桥接字段和边界见 ROOT-SOURCE-BRIDGE-PLAN.md；不额外重组巨量包直到Root实际新pins到齐。

原01实际exec79934自然OS1，在调用owner/reader/Git/锁之前，preclose拒绝合法既有空目录。Root独立failureclose58f13已实际确认整个target/Git raw/identity/member与d44 target_before相同，source885/80依赖闭合、model0。旧01/STOP及所有原件不修改。问题是控制器fileparents推导遗漏，不是payload/产品/目标漂移；原失败不能算PASS。

唯一核心修复：close_inputs.expected_dirs 在原root/publicdirs/文件祖先集合上，加入 config.target_before.directories 的**精确封存旧目录键**。已保存config中的三处实际遗漏为.git/objects/info、.git/objects/pack、.git/refs/tags。它不是任意Git目录白名单，也不忽略diff：原main sealed fullsnapshot、constructor/audit全目录登记、原target_close old identity/member检查全文保留，未新增audit/read/write/process/native/model权限。研究其余推导点：sealer.snapshot_tree和target_before包含空目录；constructor.target_directories/audit已登记全部键；finaltarget_close以before.directories为基准，均已覆盖。只有preclose这处需要补集合。

新runtime HOME为本followup02，host输出...public-review-prepare-02，seal输出...public-review-prepare-seal-02，均不复用旧namespace。sealer额外固定Root真实58f13失败关闭及原0a297 STOP，检查79934/OS1/preowner0/全target-source未改，以建立合法单次修复后继；不重发未知动作。其余source/reader/Git/FD/Job/锁/NoModel/写域保持。

作者仅JSON/AST/hash/新Task草案，未执行host/sealer/项目/Git/tests/reader/CLI/依赖/TEMP/model，未读live target/R55/nx payload。Root flags/counts/request bindings仍false/null，财务claim/model0，预算80/178/290/0。

下面只保留原运行合同和改名后的命令供后继审阅，**HOLD覆盖当前执行建议**；旧source资格不能桥到新common/journal源码，不能运行此旧epoch来生成马上陈旧的subject。

# 原public review-prepare：单一Root执行入口

本包只为 **review-prepare**：真正调用R52 `b_route_adoption.main`，固定synthetic target、operation `NativeV15Origin02` 和实际Request输入 `logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-01/request.json`。原 `capture_target`、`capture_value`、`capture_completed`、3c2原reader和原current-proof验证均不patch。它不会调用origin-prepare、review-complete、produce_proof、模型runner、claim/reservation、apply/publish或清旧锁。原native02/保护结果只作原件父链，不替代本次真实捕获。

作者仅读取源码、既存Root控制/metadata与Root150Git闭合852fa...，只做stdlib AST/JSON/hash/新控制文件组装。没有读活跃target、R55、nx实际payload、依赖、TEMP或auth/session，也未执行项目、控制器、Git、reader、CLI或模型。本包尚无实际Request raw/ready/stage pin；所有Root模板flags=false/count=null。`author_assemble.py`只用于作者AST/文本组装，STOP后拒绝再组装，**Root不需执行它或任何author_*文件**。

## 真正要运行的只有sealer和单一host

1. 先等R50独立builder及exact-x-staging真实OS0、ready/source65/target/Git闭合。当前约定stage结果是 `logs/ci/2026-11-09/story27-r52-public-request-stage-02/result.json`；还没有真实结果时不得填hash或启host。目标Request路径固定不变。若另一个真正stage namespace替代02，须新明确版本/manifest，不冒充本包已绑定。
2. Root在新Task日志域依据`Root-STOP.template.json`填写本次真实普通token、冻结源/无并行源或目标写者、原nx两锁、authenticated-capture读域及有限public scope写域的实际STOP。Root已授权动作继续自主完成；模板不是执行观察，不需向用户添加审批流程。source HEAD仍冻结30305，实际代码885原件/目录及schema65+tokenizer15+CLIpublic5由新sealer实际fresh hash/metadata闭合，作者不预签当前count。
3. Root运行metadata-only sealer（无project import、无Git/child/model）。它使用旧Root闭合config作为**有限路径/raw seed**，逐件fresh复核R52/80依赖、固定R5/R22/nx证据、Python/Git及CLIpublic DATA五件、目录、实际staged完整target/Git/Request；不会复制旧capture充当前结果。新配置只在全部真实匹配后创建一次。Root正常权限，无Fast、无main/remote操作。

```powershell
& 'C:\Program Files\Python312\python.exe' -X dev -I -S -B night-handoff/story27-r52-public-review-prepare-host-followup02/seal_review_prepare.draft.py --manifest-sha256 <THIS_REVIEWED_MANIFEST_SHA> --Root-STOP logs/ci/2026-11-09/<NEW_ACTUAL_ROOT_STOP>/Root-STOP.json --Root-STOP-sha256 <ACTUAL_STOP_SHA> --stage-receipt-sha256 <ACTUAL_STAGE02_RESULT_SHA> --request-sha256 <ACTUAL_STAGED_REQUEST_RAW_SHA> --Root-stage-OS0
```

4. 审查返回的新config路径/raw/count，再运行完整单一host。host实际载入原SourceOnly public owner并在进程内调用相当于下列唯一公开命令的原 `.main(argv)`，不另启项目CLI子进程：

```text
r52/scripts/python/b_route_adoption.py --root <exact Task/story27-r52-v15-empty-target-native01> --stage review-prepare --operation-id NativeV15Origin02 --request logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-01/request.json
```

实际Root入口：

```powershell
& 'C:\Program Files\Python312\python.exe' -X dev -I -S -B night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py --manifest-sha256 <THIS_REVIEWED_MANIFEST_SHA> --config <ACTUAL_SEAL_RETURNED_CONFIG> --config-sha256 <ACTUAL_RETURNED_RAW_SHA>
```

不要给它另加900/120秒外层控制器。本次原捕获可约40分钟，必须允许自然运行；原inner reader的**3600秒**及Job/清理/真实held终态原样保留，未缩短也未伪装无限。Root exec可用短yield回收输出而让同一进程自然继续；不因无新输出重复启动。任何超时/失败/partial/unknown都保留独立STOP，不自动重试，不读旧fixture/删旧锁。输出固定新 `logs/ci/2026-11-09/story27-r52-public-review-prepare-02`，seal固定新 `.../story27-r52-public-review-prepare-seal-02`；已存在即拒绝。

## 复用边界和必要runtime差异

- native04的SourceOnly Loader/Finder、原codec readonly FD、typed pipe、固定Python/Git、authenticated原capture准入、原transport/Job/3600和原nx锁真实调用保留。CLI helper仍原13e51字节；只把进程PATH固定到Git/Python/npm、PATHEXT=.EXE/.CMD，五个public安装原件只有DATA角色。其版本/字节或输出local catalog不证明当前模型/high/NoTools；新模型dispatch无角色，auth/session/真实.codex拒绝。
- protection03只读inventory.git原argv/env/timeout30、有限查询及真实target输出派生object provenance、两audit、原held PID/birth/image/OS-exit/stdio/close逻辑复用。Git子对象放`git_children`，不能混入原reader要求的`children==1`。新constructor只增加精确此Git分支；其它Popen仍拒绝，target locator code只读不执行。
- 旧native profile按名字拒绝prepare_review；这里仅放行真正SourceOnly `_b_route_adoption.prepare_review` 的原code/globals、固定root/op/request。所有模型、其它review/producer/origin stage继续拒绝。
- public固定可写文件只有原 `review.write_once` 的四件：`subject.json`、`w/prompt.txt`、`w/schema.json`、`request.txt`，在operation SHA256产生的原review目录，保持xb/O_EXCL/create-once。动态public锁只由真正 `_review_preview` 的 `frozen.scope_ids` → 原 `scope_guard` 调用帧派生（再加原writer:planning），原 `_directory`/coordinator_lock实际创建/加锁/解锁/关闭；不把任意logs前缀当写许可。contextmanager同一帧resume不产生第二次准入。旧nx两锁仍真实取锁；busy即真实失败，不kill/remove锁。
- review/public初始化所需有限空目录可由原函数建立；其它target73、SOURCE、capsule/support、protection、Request、Git及所有旧原件raw/identity/member不变。最终全target检查只增加四件review文件和这次实际source-derived scope锁。旧namespace/旧review存在不续跑、不覆盖。
- 原两nx锁 observer保留实际原调用参数，追加新scope锁；为closed fd整数重用保存独立历史行，避免把后一个scope错误归入前一行。所有实际路径都必须有acquire/unlock/close、无error；不假设无PID即无持有者。

## 当前结果应如何判断

原public实际returncode0/status=review_prepared，semantic_execution_required=true、machine_preservation=null、model_dispatched=false，完整subject/prompt/schema/request与runner_command/执行capture ref都来自原owner。原reader必须完整OS0+真实Job assignment/active0/close、原nx两锁实际完成；所有实际只读Git必须known terminal+stdio+closed；完整源/依赖/CLI DATA/原target/Git闭合后才写本包实际结果。仅reader OS0或JSON摘要不足。

这里只保存原runner_command描述，不执行它；没有host_review_ref或model verdict。本包的intent.json是零模型运行审计记录，**不是资金claim/新增allocation**。paid-or-unknown80/guard178/cap290/released0不变，旧unknown不释放、不重发。public review-prepare产生原preview UUID及scope锁不等于财务预留；Host1中性17/17和其Root peer也不等于真实模型已准入或预留。最终完整model-visible request/资源/资金须在此实际subject形成后由原owner和Root按合同判断。

## 静态证据限度

author-static.json列原方法AST保持、Git仅账本字段适配、完整入口AST和未执行状态。没有neutral/project测试PASS声明、没有当前实际计量、没有当前Root native/保护/Request成功预签。旧native/protection失败和原Root成功均不改。本包是可供Root审查执行的新控制候选。
