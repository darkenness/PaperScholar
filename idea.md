# 项目想法
想要参照 @PaperBanana 以及 @AutoFigure （主要是paperbanana的功能实现（因为我用过这个感觉用它的方法出来的效果很不错）同时希望能够集合同类型目 AutoFigure 的一些其他长处）实现一个专门为学术绘图打造的工具，主要面向科研人员，帮助他们快速生成高质量的学术图表。同时希望能够集成 @autofigure-edit 的功能，实现对已有图表的编辑，转换矢量图等功能。
## 项目名称
PaperScholar

## 项目背景 / 动机
科研人员在论文写作过程中，经常需要绘制各种图表来展示数据和结果。然而，手动绘制图表不仅耗时耗力，而且难以保证图表的质量和一致性。因此，需要一个专门的工具来帮助科研人员快速生成高质量的学术图表。

## 核心功能描述
1. 复现（或者改造）PaperBanana核心功能: 根据输入的method section content (Markdown recommended) and provide the figure caption，Configure settings (pipeline mode, retrieval setting, number of candidates, aspect ratio, critic rounds).自动生成学术图表Candidates（但是paperbanana的等待时间非常久，过程当中没有任何反馈交互，不知道生成什么内容，迭代图片是什么，我希望如果可以的话可以在agent交互过程当中可以把部分内容或者阶段图片映射给用户看，从而提升交互体验）
2. 复现（或者改造）AutoFigure核心功能: 对于结构化的数据，如柱状图、折线图、饼图等，参照AutoFigure以及PaperBanana的方法（像是python确定backbone，然后优化图表之类，看看已有项目怎样实现再确定具体怎样实现）
3. 复现（或者改造）AutoFigure-Edit核心功能: 支持对已有图表的编辑和优化，支持将图表转换为矢量图
4. 支持PaperBanana的精修功能（如果可以或者矢量图精修（或者部分组件精修功能））

## 目标用户
科研人员、论文作者、数据分析师等需要快速生成高质量学术图表的用户。

## 技术偏好（如有）
希望前后端分离，同时希望这个项目能够便捷部署到linux服务器上，方便后续扩展和维护。

## 其他备注
同时希望能够支持用户管理，包括用户注册、登录、权限管理等功能。用户可以申请使用系统的api，也可以使用自己的api，如果申请系统api需要管理员审核。自己的api填写后需要进行验证，确保api的有效性（可以参照 @VoAPI 的形式）。
同时对于模型调用格式，希望能够支持多种调用格式，如google anthropic openai  openai兼容格式等等，对于image模型和chat模型可以分别配置不同的url，不同api key（分离配置--可以默认使用一个url api key，但是可以自定义修改等等），不同模型名称等。
同时由于像是 PaperBanana 的流程可能过程当中会有并发的情况，所以我希望如果用户配置了多个api key（chat模型）（当然image模型也可以配置多个），可以支持负载均衡或者轮询调用。
