import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sqlite3
import os
import streamlit as st
st.write(f"実行中のStreamlitバージョン: {st.__version__}") # この行を追加

# --- Streamlit アプリの基本設定 ---
st.set_page_config(
    page_title="株価分析システム",
    layout="wide"
)

def draw_individual_stock_page(stocks_df):
    """【下段】個別銘柄分析の描画を行う"""
    # --- メインパネルでの設定 ---
    with st.expander("銘柄の設定", expanded=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            selection_method = st.radio(
                "銘柄選択方法",
                ("テーブルから選択", "手動入力"), # ラジオボタンの順序を入れ替え
                horizontal=True,
                label_visibility="collapsed"
            )
        with col2:
            if selection_method == "テーブルから選択":
                if stocks_df is not None and not stocks_df.empty:
                    # 銘柄コードと銘柄名を結合した選択肢リストを作成
                    stock_options = [f"{code} - {name}" for code, name in zip(stocks_df['銘柄コード'], stocks_df['銘柄名'])]
                    selected_stock_str = st.radio(
                        "コード",
                        options=stock_options,
                        index=0, # デフォルトで最初の銘柄を選択
                        label_visibility="collapsed"
                    )
                    ticker_symbol = selected_stock_str.split(' - ')[0] if selected_stock_str else ""
                else:
                    st.warning("上段に表示されている銘柄がありません。")
                    ticker_symbol = ""
            else: # "手動入力" の場合
                ticker_symbol = st.text_input("銘柄コード (例: 4528)", "4528", label_visibility="collapsed")

    # --- メイン処理 ---
    if not ticker_symbol:
        st.info("銘柄を選択または入力してください。")
        return

    try:
        # yfinanceで株価データを取得
        # yfinanceでデータを取得する直前に `.T` を付与する
        ticker_with_suffix = f"{ticker_symbol}.T"
        ticker = yf.Ticker(ticker_with_suffix)
        
        # 銘柄情報を取得して表示
        info = ticker.info
        # ヘッダーには `.T` を付けたティッカーシンボルを表示
        st.header(f"{info.get('longName', ticker_with_suffix)} ({ticker_with_suffix})")
        st.caption(f"業種: {info.get('sector', 'N/A')}")

        # 履歴データを取得
        df = ticker.history(period="10y") # 表示期間を10年に固定

        if df.empty:
            st.error("指定された銘柄または期間のデータを取得できませんでした。")
            return
        
        # --- 月足データの作成 ---
        # resampleを使うために、インデックスを一度datetimeに戻す
        df.index = pd.to_datetime(df.index)
        df_monthly = df.resample('ME').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        })
        # 月足移動平均線の計算
        df_monthly['SMA_5'] = df_monthly['Close'].rolling(window=5).mean()
        df_monthly['SMA_20'] = df_monthly['Close'].rolling(window=20).mean()
        df_monthly['SMA_60'] = df_monthly['Close'].rolling(window=60).mean()
        # インデックスのフォーマットを 'YYYY-MM' に変更
        df_monthly.index = df_monthly.index.strftime('%Y-%m')

        # --- 月足チャートの描画 ---
        fig_monthly = go.Figure()
        # ローソク足（陽線：白、陰線：黒）
        fig_monthly.add_trace(go.Candlestick(
            x=df_monthly.index, open=df_monthly['Open'], high=df_monthly['High'], low=df_monthly['Low'], close=df_monthly['Close'],
            name="月足",
            increasing=dict(line=dict(color='black', width=1), fillcolor='white'),
            decreasing=dict(line=dict(color='black', width=1), fillcolor='black')
        ))
        # 移動平均線（5ヶ月：赤、20ヶ月：緑、60ヶ月：青）
        fig_monthly.add_trace(go.Scatter(x=df_monthly.index, y=df_monthly['SMA_5'], mode='lines', name='5ヶ月線', line=dict(color='red')))
        fig_monthly.add_trace(go.Scatter(x=df_monthly.index, y=df_monthly['SMA_20'], mode='lines', name='20ヶ月線', line=dict(color='green')))
        fig_monthly.add_trace(go.Scatter(x=df_monthly.index, y=df_monthly['SMA_60'], mode='lines', name='60ヶ月線', line=dict(color='blue')))
        fig_monthly.update_layout(
            title=f"{info.get('longName', ticker_with_suffix)} 月足チャート",
            xaxis_rangeslider_visible=False,
            yaxis_title="株価 (JPY)"
        )
        st.plotly_chart(fig_monthly, use_container_width=True)

        st.divider() # チャート間の区切り線

        # --- ここから日足関連の表示を再追加 ---

        # --- 日足チャートの期間選択 ---
        daily_period_options = {
            "1ヶ月": 1,
            "3ヶ月": 3,
            "6ヶ月": 6,
            "12ヶ月": 12,
            "24ヶ月": 24,
        }
        selected_daily_period_label = st.radio(
            "日足チャートの表示期間",
            options=daily_period_options.keys(),
            index=1,  # デフォルトは3ヶ月
            horizontal=True
        )
        months_to_show = daily_period_options[selected_daily_period_label]

        # --- 選択された期間で日足データをスライス ---
        # 最新の日付から指定された月数だけ遡ってデータを切り出す
        end_date_for_slice = df.index.max()
        start_date_for_slice = end_date_for_slice - pd.DateOffset(months=months_to_show)
        df_daily_display = df[df.index >= start_date_for_slice].copy() # スライスしたデータで作業

        # --- 日足移動平均線の計算 ---
        df_daily_display['SMA_7'] = df_daily_display['Close'].rolling(window=7).mean()
        df_daily_display['SMA_20'] = df_daily_display['Close'].rolling(window=20).mean()
        df_daily_display['SMA_60'] = df_daily_display['Close'].rolling(window=60).mean()

        # --- 日足チャートの描画 ---
        st.subheader("日足チャート")
        fig_daily = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                  vertical_spacing=0.03, row_heights=[0.7, 0.3])

        # 日足ローソク足チャート
        fig_daily.add_trace(
            go.Candlestick(
                x=df_daily_display.index, open=df_daily_display['Open'], high=df_daily_display['High'], low=df_daily_display['Low'], close=df_daily_display['Close'],
                name="日足",
                increasing=dict(line=dict(color='black', width=1), fillcolor='white'),
                decreasing=dict(line=dict(color='black', width=1), fillcolor='black')
            ), row=1, col=1
        )
        # 日足移動平均線
        fig_daily.add_trace(go.Scatter(x=df_daily_display.index, y=df_daily_display['SMA_7'], mode='lines', name='7日線', line=dict(color='red', width=1.5)), row=1, col=1)
        fig_daily.add_trace(go.Scatter(x=df_daily_display.index, y=df_daily_display['SMA_20'], mode='lines', name='20日線', line=dict(color='green', width=1.5)), row=1, col=1)
        fig_daily.add_trace(go.Scatter(x=df_daily_display.index, y=df_daily_display['SMA_60'], mode='lines', name='60日線', line=dict(color='blue', width=1.5)), row=1, col=1)
        # 出来高
        fig_daily.add_trace(go.Bar(x=df_daily_display.index, y=df_daily_display['Volume'], name='出来高', marker_color='lightblue'), row=2, col=1)

        fig_daily.update_layout(
            title=f"{info.get('longName', ticker_with_suffix)} 日足チャート・出来高",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis_rangeslider_visible=False
        )
        fig_daily.update_yaxes(title_text="株価 (JPY)", row=1, col=1)
        fig_daily.update_yaxes(title_text="出来高", row=2, col=1)
        fig_daily.update_xaxes(type='category')
        st.plotly_chart(fig_daily, use_container_width=True)

        # --- 連続上昇・下降日数の計算 ---
        st.subheader("連続上昇・下降日数")
        st.caption("価格が移動平均線を上回っている/下回っている、または前日終値を上回っている/下回っている連続日数です。")

        def calculate_streak(condition_series):
            block = (condition_series != condition_series.shift(1)).cumsum()
            streak = condition_series.groupby(block).cumcount() + 1
            return streak * (2 * condition_series - 1)

        streak_df = pd.DataFrame(index=df_daily_display.index)
        streak_df['終値 前日比'] = calculate_streak(df_daily_display['Close'] > df_daily_display['Close'].shift(1))
        streak_df['vs 7日移動平均'] = calculate_streak(df_daily_display['Close'] > df_daily_display['SMA_7'])
        streak_df['vs 20日移動平均'] = calculate_streak(df_daily_display['Close'] > df_daily_display['SMA_20'])
        streak_df['vs 60日移動平均'] = calculate_streak(df_daily_display['Close'] > df_daily_display['SMA_60'])
        
        streak_df = streak_df[['vs 60日移動平均', 'vs 20日移動平均', 'vs 7日移動平均', '終値 前日比']]
        streak_df = streak_df.fillna(0).astype(int)

        st.dataframe(streak_df.sort_index(ascending=False))

        # 最新の株価データを表で表示（連続上昇・下降日数の下に移動）
        st.subheader("最新の株価データ")
        display_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        st.dataframe(df_daily_display[display_columns].tail().sort_index(ascending=False))

    except Exception as e:
        st.error(f"データの取得または表示中にエラーが発生しました: {e}")

def draw_all_stocks_page():
    """【上段】全銘柄分析結果の描画を行う"""
    st.header("全銘柄分析結果")
    st.caption("`stock_new.db` から読み込んだデータです。")

    # --- メインパネルでのフィルタ設定 ---
    with st.expander("表示フィルタ", expanded=True):
        col1, col2 = st.columns(2)
        flag_options = {
            "すべて": None,
            "上昇トレンド (1)": 1,
            "下降トレンド (-1)": -1
        }
        with col1:
            selected_monthly_flag_label = st.selectbox(
                "月足20_flagで絞り込み",
                options=list(flag_options.keys())
            )
        with col2:
            selected_daily_flag_label = st.selectbox(
                "日足20_flagで絞り込み",
                options=list(flag_options.keys()),
                key="daily_flag_selector"
            )
    selected_monthly_flag_value = flag_options[selected_monthly_flag_label]
    selected_daily_flag_value = flag_options[selected_daily_flag_label]

    # --- データベースからデータを読み込み ---
    try:
        # --- S3からCSVファイルを読み込む ---
        # S3のバケット名とファイル名を指定
        # 必要に応じてst.secretsなどから取得するように変更してください
        bucket_name = "your-s3-bucket-name"  # ★★★ ご自身のS3バケット名に変更してください
        file_key = "path/to/your/jpx400.csv" # ★★★ S3上のファイルパスに変更してください

        s3_path = f"s3://{bucket_name}/{file_key}"

        # PandasでS3から直接CSVを読み込む
        # 認証情報は環境変数や ~/.aws/credentials から自動で読み込まれます
        df_all = pd.read_csv(s3_path)
        st.caption(f"`{s3_path}` から読み込んだデータです。")

        # --- データの加工と表示 ---
        df_display = df_all.copy()

        # 1. フィルタリング
        # 月足フラグでの絞り込み
        if selected_monthly_flag_value is not None:
            df_display = df_display[df_display['月足20_flag'] == selected_monthly_flag_value]
        # 日足フラグでの絞り込み
        if selected_daily_flag_value is not None:
            df_display = df_display[df_display['日足20_flag'] == selected_daily_flag_value]

        # 2. カラムの順序変更
        cols = df_display.columns.tolist()
        if '出来高_前日比' in cols and '日7数' in cols:
            cols.insert(cols.index('日7数') + 1, cols.pop(cols.index('出来高_前日比')))
            df_display = df_display[cols]

        # 3. デフォルトソート
        df_sorted = df_display.sort_values('月20数', ascending=False).reset_index(drop=True)

        # 4. テーブルを表示
        st.dataframe(
            df_sorted,
            height=800 # 高さを800pxに設定
        )

        return df_sorted # ソート済みのDataFrameを返すように変更

    except Exception as e:
        st.error(f"S3からのデータ読み込み中にエラーが発生しました: {e}")

# --- メインの実行部分 ---

st.title("株価分析ダッシュボード")

# --- 上段：全銘柄分析結果を描画し、表示されているDataFrameを受け取る ---
displayed_stocks_df = draw_all_stocks_page()

st.divider() # 上段と下段を区切る線

# --- 下段：個別銘柄分析 ---
st.header("個別銘柄分析")
draw_individual_stock_page(displayed_stocks_df) # 受け取ったDataFrameを下段の関数に渡す
