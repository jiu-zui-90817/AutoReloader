# 正式版发布检查清单

## 资源
- [ ] `assets/*.ico` 已换正式设计（或确认占位可接受）
- [ ] `assets/screenshots/` 四张图已换真实截图
- [ ] README「界面预览」在 GitHub 上显示正常

## 构建
- [ ] Actions：DLL + MO/YR 启动器（带 UAC 清单）成功
- [ ] 编辑器 / 工坊 Nuitka（或当前工作流）产物可运行
- [ ] 包内无嵌套 zip；中文目录名与说明一致
- [ ] 启动器图标/盾牌（管理员）可见

## 功能冒烟
- [ ] 启动器 UAC → 注入日志有「已以管理员运行」
- [ ] 工坊：打开目录 → 改 Strength → 部署 hotfix → 游戏内重载
- [ ] 编辑器：打开工程 → 保存当前 → 备份生成；另存为仅一节、无重复 `[ID]`
- [ ] 保存文件为 UTF-8 无 BOM

## 文案
- [ ] README / 使用说明版本号与 Release tag 一致
- [ ] 不出现过时的「MO 版本号写死」等表述


## 打正式版

```bash
git tag v1.0.0
git push origin v1.0.0
```

或：GitHub → Actions → Build Release → Run workflow（填写 tag，勾选创建 Release）。

工作流**不会**因普通 push 到 main 触发。
