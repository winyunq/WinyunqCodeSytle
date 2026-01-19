import sys
import argparse

def get_visual_width(s):
    """计算字符串的视觉宽度（中文字符占2，英文字符占1）"""
    width = 0
    for char in s:
        if ord(char) > 127:
            width += 2
        else:
            width += 1
    return width

def generate_winyunq_comment(brief, params=None, return_val=None, details=None):
    """
    生成符合 Winyunq 规范的 Doxygen 块注释。
    对齐基准：
    Col 15: 描述/参数名 起始
    Col 35: 数据类型 后的类型起始
    """
    lines = ["/**"]
    
    # 1. @brief (Starts at Col 4, target Col 15)
    # " * @brief       " -> len 15
    brief_line = f" * @brief       {brief}"
    lines.append(brief_line)
    
    # 2. @details (Optional) (Starts at Col 4, tag ends at Col 13, target Col 15)
    if details:
        details_line = f" *  @details     {details}"
        lines.append(details_line)
    
    # 3. Padding line before params
    if params or return_val:
        lines.append(" * ")

    # 4. @param
    if params:
        for p_name, p_type, p_desc in params:
            # " * @param       参数名称: " -> starts at Col 4, tag ends at Col 10
            # Target Col 15 for p_name
            prefix = " * @param       参数名称: " # 15 chars if ASCII
            line_part1 = f"{prefix}{p_name}"
            
            # Target Col 35 for "数据类型:"
            current_width = get_visual_width(line_part1)
            padding_len = max(1, 35 - current_width - get_visual_width("数据类型:"))
            line = f"{line_part1}{' ' * padding_len}数据类型:{p_type}"
            lines.append(line)
            if p_desc:
                lines.append(f" *  @details     {p_desc}")

    # 5. @return
    if return_val:
        if params: lines.append(" * ")
        r_desc, r_type = return_val
        prefix = " * @return      " # 15 chars
        line_part1 = f"{prefix}{r_desc}"
        current_width = get_visual_width(line_part1)
        padding_len = max(1, 35 - current_width - get_visual_width("数据类型:"))
        line = f"{line_part1}{' ' * padding_len}数据类型:{r_type}"
        lines.append(line)

    lines.append(" **/")
    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Winyunq Comment Generator")
    parser.add_argument("--brief", required=True, help="Main brief description")
    parser.add_argument("--details", help="Detailed description")
    parser.add_argument("--param", action="append", nargs=3, metavar=("NAME", "TYPE", "DESC"), help="Parameter info")
    parser.add_argument("--returns", nargs=2, metavar=("DESC", "TYPE"), help="Return value info")

    args = parser.parse_args()
    
    comment = generate_winyunq_comment(
        args.brief, 
        params=args.param, 
        return_val=args.returns, 
        details=args.details
    )
    print(comment)
