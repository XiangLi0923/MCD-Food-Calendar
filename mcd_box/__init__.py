# -*- coding: utf-8 -*-
"""mcd_box —— 麦麦食历选餐魔盒的核心包。

模块职责（只做这几件事，不扩）：
    mcp_client  与麦当劳官方 MCP 通信（JSON-RPC over streamable HTTP）
    adapter     取数：在线拉取 / 本地缓存 / 离线快照，三种来源统一成 Catalog
    candidates  把 Catalog 变成标准 Candidate，并做份量带、多人餐等基础标注
    recommend   硬过滤 + 三条选择规则 + 差异化校验 + 随机采样（下一步）
    entry       三种入口 → 统一 Query（下一步）
    render      卡片与理由文案（下一步）
"""

__all__ = ["mcp_client", "adapter", "candidates"]
