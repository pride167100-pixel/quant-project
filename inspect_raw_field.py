def inspect(file_path, target_code, part_len):
    with open(file_path, mode="r", encoding="cp949") as f:
        for row in f:
            stock_code = row[0:9].strip()
            if stock_code == target_code:
                part2 = row[-part_len:]
                print(f"종목코드: {stock_code}")
                print(f"part2 앞 40자: {repr(part2[:40])}")
                print()
                # 0~20 구간을 4자리씩 끊어서 후보로 보여줌
                for start in range(0, 20):
                    chunk = part2[start:start+4]
                    print(f"  offset {start:2d}: {repr(chunk)}")
                return
    print("해당 종목코드를 찾지 못했습니다.")


if __name__ == "__main__":
    print("=== SK하이닉스(000660) - 전기·전자 업종이어야 함 ===")
    inspect("kospi_code.mst", "000660", 228)