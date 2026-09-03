# 隐私检测器设计

[English](privacy_detectors.md)

## 架构

```text
原始事件内容（只读）
  -> Level 0 结构化字段检测器
  -> Level 1 保守正则检测器
  -> 复合证据合并
  -> 通用个人/敏感类别
  -> 法规特定候选标记
  -> 对象级 ComplianceState
```

API 为 `Detector.detect(content, context=None) -> DetectionResult`。结果包含个人与敏感布尔值、通用类别、置信度、不含载荷的证据、检测器来源以及内容 SHA-256 指纹。不使用付费 API 或外部模型。

## 支持的通用类别

- `name`、`email`、`phone`、`address`；
- `government_identifier`、`date_of_birth`、`location`、`account_identifier`；
- `identity_document`、`financial`、`health`、`biometric`；
- `precise_location`、`minor_related`、`account_credentials`。

结构化检测使用显式字段名映射。正则检测覆盖电子邮件、保守的格式化电话号码、部分政府标识符模式以及通过 Luhn 校验的支付卡候选。它不声称能够进行通用命名实体识别。

## 证据与隐私

证据包含类别、类 JSON 路径、检测器名称、置信度和模式/字段原因，不保存匹配值。原始内容不会被修改。审计事件会对原始输入/输出进行指纹化，并脱敏敏感元数据，而不是持久化载荷。

## 法规映射

- GDPR：`health` 和符合条件的 `biometric` 信号转为 `gdpr_special_category_candidate`。
- PIPL：所有受支持的通用敏感类别转为 `pipl_sensitive_candidate`。

这些只是用于策略激活的候选，不是法律分类。例如，并非所有金融字段都属于 GDPR 第 9 条特殊类别，而 PIPL 第 28 条具有自身的敏感个人信息定义与风险门槛。

## 状态与血缘行为

每个被检测载荷属于一个 `DataObject`。没有新内容时，COPY 会保留来源分类。REDACT 与 AGGREGATE 会创建新对象 ID。有派生内容时，检测器会重新运行，并替换继承分类；因此不能仅凭转换标签是 `AGGREGATE` 就假定结果安全。

## 局限与失败风险

- 字段名可能误导、被本地化/缩写，或由攻击者控制；
- 正则可能遗漏非常规格式，也可能把偶然模式误判；
- 姓名和地址主要依赖结构化 Schema；
- 无法完整检测上下文可识别性、单独识别、间接标识符、自由文本医疗信息、族裔、信仰、性取向、政治观点和工会信息；
- 脱敏安全取决于修复内容是否真正删除标识符；检测通过不等于不可逆匿名化证明；
- 置信度是确定性启发式分数，不是经过校准的概率；
- 对抗性混淆与多模态内容不在当前检测器范围。

可选模型分类器层仍是未来扩展点；用于强制执行前，必须保留来源并完成独立评估。
