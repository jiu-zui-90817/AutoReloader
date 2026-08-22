# 图标与视觉资源

各程序需要独立 `.ico`（Windows），建议 **256×256** 主图，内含 16/32/48/256 多尺寸。

## 建议设计方向（统一工具链）

| 程序 | 文件名 | 风格建议 |
|------|--------|----------|
| INI 工程编辑器 | `editor.ico` | 文档/代码块 + 轻微「齿轮或铅笔」；主色深蓝/青 |
| 战术工坊 | `workshop.ico` | 扳手/滑块/快调面板；主色橙或琥珀 |
| AutoReloader（通用） | `reloader.ico` | 循环箭头 + 小「INI」或闪电图标；主色绿 |
| MO 启动器 | `launcher_mo.ico` | 与 MO 黑红/盟军风格可区分，仍带循环/注入暗示 |
| YR 启动器 | `launcher_yr.ico` | 与 YR 经典黄/棕或紫相区分 |

### 原则
1. **同一工具链**：共用圆形/圆角方形底、细描边，避免五套完全不相关的风格。
2. **小尺寸可辨**：16×16 仍能看出「编辑 / 工坊 / 启动」差异。
3. **不要用游戏官方 Logo** 作为主图标（版权）；可用抽象几何。
4. 导出为真正的 **Windows ICO**（不是只把 png 改后缀）。

### 制作方式（任选）
- Figma / Affinity / Photoshop → 导出 PNG → [icoconvert.com](https://icoconvert.com) 或 ImageMagick：  
  `magick icon-256.png -define icon:auto-resize=256,128,64,48,32,16 app.ico`
- 也可用开源图标（MIT）再上色重组。

放好后路径约定：

```text
assets/editor.ico
assets/workshop.ico
assets/reloader.ico
assets/launcher_mo.ico
assets/launcher_yr.ico
```

Nuitka / 启动器工作流会在文件存在时自动嵌入；缺失则跳过图标，不影响编译。
