"""New original regression cases; kept separate from the initial fixture builder."""
EXTENDED = r'''

<!-- pagebreak -->
## T12 内容列宽与短表达

预期：序号列较窄，说明列较宽；英文单词、12.50 mV、1.25e-3 A 和数字 123.456 尽量整体换行，最后的“结束标记”不丢失。

| 编号 | 测量 | 说明 |
|---|---|---|
| 01 | 12.50 mV | reconstruction sample 的中文长说明，自动分配更多空间，结束标记。 |
| 02 | 1.25e-3 A | 数字 123.456 与 unit test 均保持顺序。 |

## T13 公式安全分行

预期：只在顶层运算符前分行，拼回源字符串后完全相同；分数、根式、括号、上下标和矩阵内部不拆。

$$R=\frac{a_1+b_1}{c_1-d_1}+\frac{a_2+b_2}{c_2-d_2}+\frac{a_3+b_3}{c_3-d_3}+\frac{a_4+b_4}{c_4-d_4}+\sqrt{u_1+v_1}+(p_1-q_1)+t_{i+1}+\frac{a_5+b_5}{c_5-d_5}+\frac{a_6+b_6}{c_6-d_6}+\frac{a_7+b_7}{c_7-d_7}$$

预期：下式的大分组中没有可靠断点，允许整体缩放，但必须报告不能分行的原因与比例。

$$\left(\frac{a_1+b_1}{c_1}+\frac{a_2+b_2}{c_2}+\frac{a_3+b_3}{c_3}+\frac{a_4+b_4}{c_4}+\frac{a_5+b_5}{c_5}+\frac{a_6+b_6}{c_6}+\frac{a_7+b_7}{c_7}+\frac{a_8+b_8}{c_8}+\frac{a_9+b_9}{c_9}+\frac{a_{10}+b_{10}}{c_{10}}\right)$$

<!-- keep-next -->
### T14 标题与显式图注组合

![替代文字](assets/small.png)
<!-- caption: 显式图注替代图片替代文字，标题、图、图注应在同页。 -->

预期：上面的 keep-next 只绑定之后两块；普通说明段落不自动绑定。下面两张连续图片及各自图注应保持各自组合，不出现孤立图注。

![第一张](assets/small.png)
<!-- caption: 连续图片一。 -->
![第二张](assets/wide.png)
<!-- caption: 连续图片二。 -->

<!-- pagebreak -->
## T15 超高组合稳定降级

预期：两张高图组合超过一页，只给出明确降级提示并按顺序分页，保留两张完整图和两个图注；末尾连续分页标记不生成空白页。

<!-- keep-start -->
![高图一](assets/tall.png)
<!-- caption: 超高图一，边框完整。 -->
![高图二](assets/tall.png)
<!-- caption: 超高图二，边框完整。 -->
<!-- keep-end -->
<!-- pagebreak -->
<!-- pagebreak -->
'''

COMPARISON = r'''# 短示例：同字与清晰图表

的的的的的的的的　人人人人人人人人

English words: reconstruction, 12.50 mV, 123.456.

行内 $a_i^2+\frac{b}{\sqrt{c}}$ 与正文混排。

$$E=\frac{a+b}{c}+\sqrt{1+x^2}$$

| 项目 | 值 | 说明 |
|---|---|---|
| 的的的 | 12.50 mV | handwriting sample |
| 人人人 | $x^2$ | 清晰表格 |

```diagram
     ↑ Q
 ×   │   ×
┄┄┄┄┄┼┄┄┄┄┄
─────┼─────→ I
 ×   ┆   ×
```
'''
