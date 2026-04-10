"""
アプリケーションアイコン（.ico）を生成するスクリプト
"""
from PIL import Image, ImageDraw


def create_bank_icon():
    """銀行風アイコンを複数サイズで生成"""
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # スケール係数
        s = size / 64.0

        # 屋根（三角形）
        draw.polygon([
            (int(32 * s), int(4 * s)),
            (int(4 * s), int(24 * s)),
            (int(60 * s), int(24 * s))
        ], fill='#1a5276')

        # 建物本体
        draw.rectangle([
            int(8 * s), int(24 * s), int(56 * s), int(56 * s)
        ], fill='#2c3e50')

        # 柱
        col_width = max(1, int(4 * s))
        for cx in [16, 26, 36, 46]:
            x = int(cx * s)
            draw.rectangle([
                x, int(28 * s), x + col_width, int(52 * s)
            ], fill='#ecf0f1')

        # 土台
        draw.rectangle([
            int(4 * s), int(56 * s), int(60 * s), int(62 * s)
        ], fill='#1a5276')

        # 円（¥マーク用の背景）
        center = int(32 * s)
        r = int(8 * s)
        draw.ellipse([
            center - r, int(34 * s) - r,
            center + r, int(34 * s) + r
        ], fill='#f39c12')

        images.append(img)

    # .ico として保存（複数解像度を含む）
    images[0].save(
        "kagin_icon.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print("kagin_icon.ico を生成しました")


if __name__ == "__main__":
    create_bank_icon()
