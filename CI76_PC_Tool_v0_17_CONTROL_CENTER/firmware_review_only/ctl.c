/* ========================================================================
 *      INCLUDE
 * ======================================================================== */
#include "main.h"
#include "adc.h"
#include <stdio.h>
#include "ctl.h"
#include "stm32g0xx_it.h"
#include "math.h"
#include "pid.h"
#include "flash.h"
#include "uart.h"
#include "ics.h"
#include "pvt.h"
/*  ========================================================================
 *      DEFINELUDE
 *  ========================================================================  */
#define OC_L	0x01
#define OC_H	0x02
//Hall sensor GPIO ports and pins
#define HALL_SENSOR_PORTC GPIOC
#define HALL_SENSOR_PIN6 GPIO_PIN_6
#define HALL_SENSOR_PIN7 GPIO_PIN_7
//POT GPIO port and pin
#define M1_POT_GPIO_PORT   GPIOB
#define M1_POT_GPIO_PIN    GPIO_PIN_11
//motor status
#define MOTOR_STOP      0
#define MOTOR_BRAKE     1
#define MOTOR_FAST_UP   2
#define MOTOR_SLOW_UP   3
#define MOTOR_FAST_DN   4
#define MOTOR_SLOW_DN   5
//learning par
#define LEARN_FAST_PWM          1900	//100%
#define LEARN_SLOW_PWM          500		//25%
#define LEARN_BACK_PWM          700		//35%

#define LEARN_BACK_COUNT_HALL   80
#define LEARN_BACK_COUNT_POT    20
#define LEARN_BACK_MAX_MS       500

#define LEARN_STOP_PWM_TH       30
#define LEARN_WAIT_MS           300
#define LEARN_CONFIRM_MS        100

#define LEARN_FAST_TO_LIMIT     0
#define LEARN_WAIT_AFTER_FAST   1
#define LEARN_BACK_OFF          2
#define LEARN_WAIT_AFTER_BACK   3
#define LEARN_SLOW_TO_LIMIT     4
#define LEARN_WAIT_AFTER_SLOW   5
// =======================================================

/*  ========================================================================
 *      ENUMERATION
 *  ========================================================================  */

/*  ========================================================================
 *      STRUCT
 *  ========================================================================  */

/* ========================================================================
 *      VARIABLE
 * ======================================================================== */
extern ADC_HandleTypeDef hadc1;  // ADC handler
extern DMA_HandleTypeDef hdma_adc1;
extern TIM_HandleTypeDef htim3;  //TIM3
extern TIM_HandleTypeDef htim1;//PWM timer
extern TIM_HandleTypeDef htim16; //input PWM timer
extern adc_t adc;
extern system_t sys;
extern flash_save_t fs;
extern pctool_t PCTL;
extern ics_t ics;
//control source
control_SRC_t g_active_src = SRC_none;
uint8_t  has_uart = 0, has_hand = 0, has_vc = 0, has_ic = 0, has_rc = 0;
//input mode
inputmode modestate = mode_none;
motorpwm motorstate = motor_idle;
uint16_t mode_value = 0;
// rc servo
rc_input_t rc = {0}; // rc servo init
//pwm
m_t m1;
int32_t pwm = 0;
int32_t	i = 0;
int32_t ccra = 0;
int32_t ccrb = 0;
//pid
pid_t pid;
//control
uint8_t testmode = 0; //mode control
uint8_t cmd = 0;
press_t pt; // button press
press_t pt_cmd1 = { .need = 5, .count = 0, .gap_ms = 600, .last_ms = 0 }; // 用於 電流控制
press_t pt_cmd2 = { .need = 5, .count = 0, .gap_ms = 600, .last_ms = 0 }; // 用於 速度控制
//pos
position_t pos;
int32_t T1;		//誤差精度
int32_t T2;		//煞車時間 = 誤差精度 * 2
int32_t SLOW; //最低速(PWM)
int32_t acc;	//緩起停時間ms
int32_t posErr;
//hall
hall_t hall;
//option
option_t op;
uint8_t last_button_state = 0;
uint8_t last_sensor_mode = 0xFF;
//button
uint32_t keyTime;
uint8_t keyDebounce[4];
uint8_t key = 0;
uint8_t keyTrg = 0;
uint8_t keyCont = 0;
//uint8_t ce_butten = 0;
////ICS
//ics_t ics;
//learning
learn_t ln;
int32_t go_home_after_learn = 0;
//flash
uint32_t flash_tick = 0; //flash clock
pot_t pot;
//CNT
uint8_t exVoltErr = 0;
uint8_t exCurErr = 0;
uint8_t exPosErr = 0;
uint8_t exErrCode = 0;

void pwminit(void)
{
		HAL_TIM_Base_Start(&htim1);
		HAL_TIM_Base_Start_IT(&htim3);
		HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_1);
    HAL_TIM_PWM_Start(&htim1, TIM_CHANNEL_2); 
		flash_tick = HAL_GetTick();
	
		//hall sensor
		hall.spe_count = 0;
    hall.spe_gap = 10000; // 初速度為0
	
		///motor init
		m1.mc = 0;
		m1.arr = &(TIM1->ARR);
		m1.ccra = &(TIM1->CCR1);
		m1.ccrb = &(TIM1->CCR2);
		m1.ccer = &(TIM1->CCER);
		m1.ccerMask = 0x00001055; //1+1N,2+2N,channel 4
		TIM1->CCER |= m1.ccerMask;
		
		TIM1->BDTR |= TIM_BDTR_MOE;
	
		testmode = 2;
	
		m1.pwm_max = 1900; // 95% pwm
		
		m1.setcur = 3500;	//限電流
		m1.cur_overload = 5000;    //過載電流 mA//MD66 2700ma//LD3 1600ma //mk32 no load:2500 full load:5200 //ID10 no load:500 full load:5500 //mks1 no load:	150 full load:400	
		m1.cur_overload_time = 0;
		m1.cur_ot_set = 500; //過載電流時間 ms
		m1.cur_pid.kp = 300;
		m1.cur_pid.ki = 2000;
		
		m1.cur_flt.kp = 200;
		m1.ma_flt.kp = 200;
		m1.mb_flt.kp = 200;
		m1.pot_flt.kp = 200;
		m1.spe_flt.kp = 200;
		m1.mv_flt.kp = 200;
		m1.rc_flt.kp = 200;
		m1.dp_cur_flt.kp = 200; 
		op.button = 0;
		op.sen_hall = 0;
		op.sen_pot = 0;
		
		m1.pvstate = hallsensor_readraw(&m1);
		m1.curstate = m1.pvstate;
		m1.hall_pos = 0;
		m1.hall_min = -200000;
		m1.hall_max =  200000;
    m1.motor_en = 0;
		m1.motor_last_pos = 0;
    m1.hall_lasttick = HAL_GetTick();
		
		ln.learningmode = 0;
		ln.learnstarttime = 0;
		ln.last_ramp_time = 0;
		ln.curtime = 0;
		ln.learnstep = 0;
		ln.pos_max = 0;
		ln.pos_min = 0;
		ln.learningmode = 0;
//		ln.spe = 1140;	// learning speed pwm = 60% * 1900
		ln.spe = 1900;	// learning speed pwm = 60% * 1900
    
		pos.max = 0;
		pos.min = 0;
		pos.setmax = 90;	//0 - 1000 = 0 - 100%
		pos.setmin = 10; //0 - 1000 = 0 - 100%
		pos.softstroke = 0;
		pos.hardstroke = 0;
    pos.acc = 0;
		pos.acc_x200  = 10;  // 0 - 200 = 0 - 20%
    pos.dead_zone = 10;
		pos.diff = 0;
	  pos.target = 0;
		pos.last_hall_pos = 0;
		pos.last_pot_pos = 0;	
		pos.decided = 0;
		
		// POS + PI
		m1.vel_mm_s_x1000 = 0;
		
		T1 = 25;
		SLOW = 700;	
		posErr = 0;
		acc = 0;
		
		pot.w = 2;
		pot.spe_gap = 1000;		//原本是16000
		pot.center = m1.potAvg;
		pot.last_center = m1.potAvg;
    pot.spe_count = 0;
		pot.diff = 0;
		
			
		flash_load();  //讀取上次參數
	
		config_sensor_gpio();

		if (op.sensormode == 0)
		{
				m1.pvstate = hallsensor_readraw(&m1);
				m1.curstate = m1.pvstate;
		}
		
}
void pwmloop(void)
{
		if (pvt.mode != PVT_MODE_NORMAL)
    {
        return;
    }
			// 判斷是否持續按住 EN 且 cmd == 0x03
		if (((ics.en == GPIO_PIN_RESET) && (cmd == 0x03)) || testmode == 4 || PCTL.ln_mode == 0x01)
		{
			if (ln.learntick == 0)
			{
					ln.learntick = HAL_GetTick(); // 第一次觸發時記錄時間
			}
			else if ((HAL_GetTick() - ln.learntick >= 2000 && ln.learningmode == 0))
			{
					// 已經持續 2 秒，觸發學習模式
					testmode = 2;
					PCTL.ln_mode = 0x01;
					PCTL.pos_ctlmode = 0x00;
					ln.old_mode = PCTL.ln_mode;
					ln.learningmode = 1;
					ln.learnstarttime = HAL_GetTick();
                    ln.error = 0; // Begin a NEW learn transaction; do not inherit prior failure.
                    pos.need_learn = 1;

					// before starting clear
					pos.min = 0;
					pos.max = 0;
					pos.softstroke = 0;
					pos.hardstroke = 0;
					pos.target = 0;
					ln.pos_min = 0;
					ln.pos_max = 0;
					ln.curtime = 0;
					ln.learnstep = 0;
			}
		}
		else
		{
			// 條件不成立時清除記錄
			ln.learntick = 0;
		}
			if (ln.learningmode == 1)
			{
					if (HAL_GetTick() - ln.learnstarttime >= 2000)
					{
							ln.learningmode = 2;
							ln.learnstep = 0;
					}
					    ln.cur            = 0;
							ln.dp_pos         = 0;
							ln.last_pos       = m1.pos;   // 以目前位置當 baseline
							ln.still_ms       = 0;
							ln.still_delta_ms = 0;
							ln.run_cur        = 0;
			}
			//learning mode
			if (ln.learningmode == 2)
			{
					learnHandler(&m1);
					//sys.MotorStatus = 0x05;
				  if(ln.old_mode == 0x01 && PCTL.ln_mode == 0x00)
					{
							ln.error = 1;
					}
					uint8_t fatal_err0 = sys.errBit0 & ~(ERR_POS_FEEDBACK); // 學習過程中允許 POS_FEEDBACK 存在
					// stop learning
				  if (((cmd == 0x01 || cmd == 0x02) && cmd != 0x03) || modestate != mode_none || PCTL.pos_ctlmode != 0x00 || (fatal_err0 != 0u) || (sys.errBit1 != 0u))
				  {
							ln.error = 1;
				  }
					if(ln.error)
					{
						  ln.learningmode = 0;
							ln.learnstep = 0;
							ln.curtime = 0;
							ln.pos_min = 0;
							ln.pos_max = 0;
                            pos.need_learn = 1;
                            sys.errBit0 |= ERR_POS_FEEDBACK;
							testmode = 2;
                            m1.motor_en = 0;
                            m1.speCmd = 0;
                            m1.pwmReq = 0;
                            m1.pwm_x1024 = 0;
							m1.curCmd = 0;
							pos.softstroke = 0;
							pos.hardstroke = 0;
							pos.target = 0;
							//sys.MotorStatus = 0x01;
							PCTL.ln_mode = 0x00;
							PCTL.pos_ctlmode = 0x00;
							sys.errBit0 |= ERR_LEARN_FAIL;
					}
			}
		if(op.sensormode == 0){op.sen_pot = 0; op.sen_hall = 1;}
    if(op.sensormode == 1){op.sen_pot = 1; op.sen_hall = 0;}
		// 根據 sensormode 只切換一次 GPIO 設定
		static uint8_t last_sensormode = 0xFF;
		if (op.sensormode != last_sensormode) 
		{
				config_sensor_gpio();

				/*
				 * Hall 模式切入時，重新同步 Hall 狀態，
				 * 避免剛切換瞬間 pvstate 還停在舊值造成非法跳轉。
				 */
				if (op.sensormode == 0)
				{
						m1.pvstate = hallsensor_readraw(&m1);
						m1.curstate = m1.pvstate;
						hall.spe_count = 0;
						hall.spe_gap = 10000;
				}

				last_sensormode = op.sensormode;
		}
		// 位置來源切換
		if (op.sen_hall == 1)
		{	
			m1.pos = m1.hall_pos;
		}
		else
		{
			m1.pos = m1.potAvg;
		}
		
    // hand control
    if((HAL_GetTick() - keyTime) > 10)
    {
        keyTime = HAL_GetTick();
				
        keyDebounce[3] = keyDebounce[2];
        keyDebounce[2] = keyDebounce[1];
        keyDebounce[1] = keyDebounce[0];
        keyDebounce[0] = !HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_4);
        keyDebounce[0] += !HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_5) << 1;

        key = keyDebounce[0] & keyDebounce[1] & keyDebounce[2] & keyDebounce[3];
        keyTrg = key & (key ^ keyCont);
        keyCont = key;
        cmd = keyCont & 0x03;
			
#if CI76_DEBUG_HOOK
        /* HardFault 測試：按住 I1 讓馬達運轉時，再按 CLR */
//        if (ics.clr == GPIO_PIN_RESET && (keyCont & 0x01))
//        {
//            *(volatile uint32_t *)0x20000001 = 0;   // 未對齊寫入 → HardFault
//        }
        /* 故障注入測試（量產版 CI76_DEBUG_HOOK 必須為 0） */
        if (ics.clr == GPIO_PIN_RESET && keyCont == 0x01) { *(volatile uint32_t *)0x20000001 = 0; }  // I1 + CLR：HardFault
        if (ics.clr == GPIO_PIN_RESET && keyCont == 0x02) { while (1) { } }                          // I2 + CLR：主迴圈卡死
        if (ics.clr == GPIO_PIN_RESET && keyCont == 0x03) { NVIC_DisableIRQ(TIM3_IRQn); }            // I1 + I2 + CLR：TIM3 中斷停止
#endif
	
				uint32_t press_now_ms = HAL_GetTick();
				// non mode 暗控
				if(testmode == 0) 
				{
						if (presscontrol(&pt_cmd1, 0x01, cmd, keyTrg, press_now_ms)) {testmode = 1;}
						else if (presscontrol(&pt_cmd2, 0x02, cmd, keyTrg, press_now_ms)) {testmode = 2;}
						else
						{
								m1.controlmode = testmode;
								m1.motor_en = 0;
								m1.curCmd = 0;
								m1.speCmd = 0;
								m1.posCmd = 0;
						}
				}
			
				//cur mode
				if(ics.en == GPIO_PIN_RESET && testmode == 1)
				{
					m1.controlmode = 1;

					if((sys.errBit0 == 0u) && (sys.errBit1 == 0u))
					{
							m1.motor_en = 1;
							if(ln.learningmode == 0)
							{
									if(op.button == 0)// 按鈕控制
									{										
											if(cmd == 0x01 || cmd == 0x02)
											{												
													m1.motor_en = 1; 
													m1.curCmd = (cmd == 0x01) ? m1.setcur : -m1.setcur;
											}
												//10A測試用
//											else if(PCTL.pos_ctlmode == 0x02 || PCTL.pos_ctlmode == 0x03)
//											{
//													m1.motor_en = 1;
//													m1.curCmd = (PCTL.pos_ctlmode == 0x02) ? m1.setcur : -m1.setcur;
//											}
											else
											{
													m1.curCmd = 0;
													pwm = 0;
													m1.pwm_set = 0;
											}
									}
							}
							else if(ln.learningmode != 2)
							{
									m1.curCmd = 0;
									pwm = 0;
									m1.pwm_set = 0;
							}
					}
					else
					{
							// 發生錯誤或警報，強制關閉
							m1.curCmd = 0;
							m1.pwm_set = 0;
					}
				}
				
							
				if(testmode == 2 || testmode == 3)
				{
					m1.speset_x1000 = sys.speset * 10;
					m1.spetar = (m1.speset_x1000 * m1.pwm_max) / 1000;
					if(m1.spetar >= 1900){m1.spetar = 1900;}
					if(m1.spetar < 1900 && m1.spetar > 0 ){m1.spetar = (m1.speset_x1000 * m1.pwm_max) / 1000;}
					if(m1.spetar <= 0){m1.spetar = 0;}

					if(m1.spetar > 0 && testmode == 3) 
					{
							int32_t MIN_SLOW = 50;
							int32_t slow_prop = 500;
							if(m1.spetar <= MIN_SLOW){SLOW = 0;} 
							else 
							{
									SLOW = slow_prop;
									if(SLOW <  MIN_SLOW){SLOW = MIN_SLOW;}
									if(SLOW >  m1.spetar){SLOW = m1.spetar;}
							}
					} 
					else {SLOW = 0;}

				}
				else
				{
					m1.speset_x1000 = 0;
					m1.spetar = 0;
				}
				// spe mode
				if(ics.en == GPIO_PIN_RESET && testmode == 2)
				{
						m1.controlmode = 2;

						uint8_t fatal_err =
								((sys.errBit0 & ~(ERR_POS_FEEDBACK)) != 0u) ||
								(sys.errBit1 != 0u);

						// learning mode
						if(ln.learningmode == 2)
						{
								if(!fatal_err)
								{
										m1.motor_en = 1;
								}
								else
								{
										m1.motor_en = 0;
										m1.speCmd = 0;
								}
						}

						// normal CE mode
						else
						{
								if(!fatal_err)
								{
										m1.motor_en = 1;

										if((op.button == 0) &&(cmd == 0x01 || cmd == 0x02))
										{
												m1.speCmd =
														(cmd == 0x01) ?
														 m1.spetar :
														-m1.spetar;

												m1.speInc_x1024 = 30000;
										}
										else
										{
												m1.speCmd = 0;
												m1.speInc_x1024 = 30000;
										}
								}
								else
								{
										m1.speCmd = 0;
										m1.speInc_x1024 = 30000;
								}
						}
				}

				// pos mode
				if(pos.need_learn && testmode == 3){testmode = 2;}
        if(ics.en == GPIO_PIN_RESET && testmode == 3)
        {
						pos_soft();
            m1.controlmode = testmode;
					
						has_hand = (cmd == 0x01 || cmd == 0x02) ? 1 : 0;
						update_uart_activity();     // 偵測 UART 是否有設定目標（活躍）

						if(!arbitrate_control_source()) 
						{
							return;
						}
						control_source_selection();	//選擇操作模式
						position_control(&m1);
        }
    }
		motor_time();
		pos_memory();
}

void pwm_set(m_t* m)
{
	if(m->motor_en == 1)
	{
		if(m->pwmOn == 0)
		{
			uint32_t ccr, ccer;
			
			ccr = *m->arr / 2;
			*m->ccra = ccr;
			*m->ccrb = ccr;
			
			ccer = *m->ccer;
			ccer |= m->ccerMask;
			*m->ccer = ccer;
			
			m->pwmOn = 1;
		}
		else
		{
			pwm = constrain(m->pwm_set, -1900, 1900); //voltage compensation
	
			
			ccra = 1000 + (pwm / 2);
			ccrb = 1000 - (pwm / 2);
			
			if(pwm > 0) {ccra += pwm % 2;}
			if(pwm < 0) {ccrb -= pwm % 2;}
			
			*m->ccra = constrain(ccra, 0, 1900); //max pwm duty = 95%
			*m->ccrb = constrain(ccrb, 0, 1900);
		}
	}
	else
	{
		uint32_t ccr, ccer;
		
		ccr = *m->arr / 2;
		*m->ccra = ccr;
		*m->ccrb = ccr;
		
		ccer = *m->ccer;
		ccer &= ~(m->ccerMask);
		*m->ccer = ccer;
		
		m->pwmOn = 0;
	}
}

void currentControl(m_t* m)
{
	// cur mode
    if(m->controlmode == 1 && m1.motor_en == 1)
    {
        m->pwm_set = pi_control_1016( &m->cur_pid, (m->curCmd - m->curAvg), -1900,1900);
    }

	 
	//spe mode
		else
		{
			if(m->cur_flag == 0)
			{
				if(abs(m->cur) <= m->setcur) {m->pwm_set = pi_control_1016_Set(&m->cur_pid, m->pwmReq);}
				else if(m->cur < -m->setcur) {m->cur_flag |= OC_L;}
				else if(m->cur >  m->setcur) {m->cur_flag |= OC_H;}
			}
			if(m->cur_flag & OC_L)
			{
				m->pwm_set = pi_control_1016(&m->cur_pid, (-m->setcur - m->curAvg), -1900, 1900);
				if(m->pwm_set <= m->pwmReq) {m->cur_flag &= ~(OC_L);}
			}
			if(m->cur_flag & OC_H)
			{
				m->pwm_set = pi_control_1016(&m->cur_pid, ( m->setcur - m->curAvg),  -1900, 1900);
				if(m->pwm_set >= m->pwmReq) {m->cur_flag &= ~(OC_H);}
			}
		}
}

void speedControl(m_t* m)
{
	if (ln.learningmode == 2)
	{
			int32_t cmd = constrain(m->speCmd, -m->pwm_max, m->pwm_max);

			m->pwmReq     = cmd;
			m->pwm_x1024  = cmd * 1024;
	}
	if(PCTL.set_mode == 0x00 && PCTL.ext_acc_ms != 0)
	{
			acc = PCTL.ext_acc_ms;
	}
	else
	{
			acc = 500;
	}
	
	//spe mode
	m->speInc_x1024 = constrain(m->speInc_x1024, 1, 100000);
	
	if(m->speCmd == 0)
	{
			if(m->pwm_x1024 == 0) {m->pwm_x1024 = 0;}
			else if(m->pwm_x1024 > 0) {m->pwm_x1024 = max(0, m->pwm_x1024 - m->speInc_x1024);}
			else if(m->pwm_x1024 < 0) {m->pwm_x1024 = min(0, m->pwm_x1024 + m->speInc_x1024);}
	}
	else if(m->speCmd > m->pwm_set)
	{
			m->pwm_x1024 = min(m->pwm_x1024 + m->speInc_x1024, min((m->speCmd * 1024),  2048000));
	}
	else if(m->speCmd < m->pwm_set)
	{
			m->pwm_x1024 = max(m->pwm_x1024 - m->speInc_x1024, max((m->speCmd * 1024), -2048000));
	}
	
	m->pwmReq = m->pwm_x1024 / 1024;
}

void speHandler(m_t* m)
{
	if(op.sen_hall == 1)
  {
			int32_t dir = constrain(m->pwm_set, -1, 1);	
			int32_t gap = hall.spe_gap;
			if(gap < 1) gap = 1; 

			m->spe = filterLp(&m->spe_flt, 16000 * dir / gap); 	//hall speed
  }
	else if(op.sen_pot == 1)
	{
			potHandler(&m1);
			m->spe = filterLp(&m->spe_flt, (1000 * pot.diff) / pot.spe_gap);   // 原本 16000
	}
}

void potHandler(m_t *m)
{
    if (pot.spe_count < 1001) pot.spe_count++;		// 原本 16001；都約等於 1 秒
    if (pot.spe_count > pot.spe_gap) pot.spe_gap = pot.spe_count;
	
    //動態框(w)
    if (m->potAvg > pot.center + pot.w || m->potAvg < pot.center - pot.w)
    {
        pot.spe_gap = pot.spe_count;
        if (pot.spe_gap == 0){pot.spe_gap = 1;} // 保底
        pot.spe_count = 0;
        pot.diff = m->potAvg - pot.center;
        pot.last_center = pot.center;
        pot.center = m->potAvg;
    }
}

void pos_soft(void)
{
    pos.hardstroke = ln.pos_max - ln.pos_min;                  // 硬體行程
    pos.min        = ln.pos_min + (pos.hardstroke * pos.setmin) / 100;	//20250909 0 -100% = 0 - 1000
    pos.max        = ln.pos_min + (pos.hardstroke * pos.setmax) / 100; //20250909 0 -100% = 0 - 1000
    pos.softstroke = pos.max - pos.min;																 //軟體行程
    pos.acc        = (abs(pos.hardstroke) * pos.acc_x200) / 1000; // 精度誤差
}

int32_t PCTL_accmin(int32_t ramp_ms)
{
    /*
     * PC Tool 允許顯示/儲存 0。
     * 但內部除法不能用 0，所以 0 代表最快速，內部用 1ms 計算。
     */
    if (ramp_ms <= 0)
    {
        return 1;
    }

    return ramp_ms;
}

void position_control(m_t *m)
{
		if (pos.need_learn)	//需學習才能夠位置控制
    {
        m->speCmd = 0;
        m->speInc_x1024 = 30000;
        pos.target = m->pos;
        PCTL.pos_ctlmode = 0x00;
        return;
    }

		if (m1.spetar <= 0 || (sys.errBit0 != 0u) || (sys.errBit1 != 0u)) 
		{
				m->speCmd = 0;
				m->speInc_x1024 = 30000;
				m->controlState = MOTOR_STOP;
				pos.target = m->pos;
				PCTL.pos_ctlmode = 0x01;
				return;
		}
		 // 防呆
		if (pos.max <= pos.min || (pos.max - pos.min) < 10)
		{
				m->speCmd = 0;
				return;
		}

		if (ln.pos_max > ln.pos_min)  // 防呆
		{
				pos.dp_pos = ((m1.pos - ln.pos_min) * 1000) / (ln.pos_max - ln.pos_min);
				pos.dp_pos = constrain(pos.dp_pos, 0, 1000);	// 顯示位置 0–100%
		}
		else
		{
				pos.dp_pos = 0; // 無效狀態
		}

		if (go_home_after_learn) 
		{
				pos.target = pos.min;
				
				if (abs(m->pos - pos.min) <= max(pos.acc, pos.dead_zone)) 
				{
						go_home_after_learn = 0;
						PCTL.pos_ctlmode = 0x00;

						flash_save();
				}
		}
		
		else if (op.button == 0)
		{
				if(op.tool == 0)
				{
						if(cmd == 0x01){pos.target = pos.max;}
						else if (cmd == 0x02){pos.target = pos.min;}
						else
						{
								pos.target = m->pos;
								m->posTrg = m->pos;

								m->controlState = MOTOR_STOP;

								m->speCmd = 0;
								m->speInc_x1024 = 30000;

								m->pwm_x1024 = 0;
								m->pwmReq = 0;
								m->pwm_set = 0;

								return;
						}
				}
		else if (op.tool == 1)
		{
				// pc tool button
				if(PCTL.pos_ctlmode == 0x02){pos.target = pos.max;}
				else if(PCTL.pos_ctlmode == 0x03){pos.target = pos.min;}
				else if(PCTL.pos_ctlmode == 0x01)
				{
						pos.target = m->pos;
						m->posTrg = m->pos;

						m->controlState = MOTOR_STOP;

						m->speCmd = 0;
						m->speInc_x1024 = 30000;

						m->pwm_x1024 = 0;
						m->pwmReq = 0;
						m->pwm_set = 0;

						PCTL.pos_ctlmode = 0x00;
					
						return;
				}
				// pc tool %
				else if(PCTL.pos_ctlmode == 0x04)
				{
						pos.target = ln.pos_min + (pos.hardstroke * m->posCmd) / 100;
				}
				else
				{
						pos.target = m->pos;
				}
		}
		}
		else if (op.button == 1)
			{
				// input mode			
				mode_value = constrain(mode_value, pos.setmin * 10, pos.setmax * 10);
				pos.target = ln.pos_min + (pos.hardstroke * mode_value) / 1000;
		}
		else
		{
				m->speCmd = 0;
				pos.target = m->pos;
				return;
		}
		//new position control
		m->dist = (m->spe * m->speCmd) / (m->speInc_x1024 * 2);
		T1 = pos.acc;
		T2 = T1 * 2;
		switch(m->controlState)
		{
			case MOTOR_STOP:
			{
				posErr = pos.target - m->pos;
				if(posErr >  T2) {m->controlState = MOTOR_FAST_UP;}
				if(posErr < -T2) {m->controlState = MOTOR_FAST_DN;}
				break;
			}
			
			case MOTOR_BRAKE:
			{
				if(m->pwmReq == 0) {m->controlState = MOTOR_STOP;}
				break;
			}
			
			case MOTOR_SLOW_UP:
			{
						 if ((pos.target + T2) < m->pos)    {m->controlState = MOTOR_FAST_DN;}
				else if ((pos.target - T2) > m->posTrg) {m->controlState = MOTOR_FAST_UP;}
				else if ((pos.target - T1) < m->pos)    {m->controlState = MOTOR_BRAKE;}
				break;
			}
			
			case MOTOR_SLOW_DN:
			{
						 if ((pos.target - T2) > m->pos)    {m->controlState = MOTOR_FAST_UP;}
				else if ((pos.target + T2) < m->posTrg) {m->controlState = MOTOR_FAST_DN;}
				else if ((pos.target + T1) > m->pos)    {m->controlState = MOTOR_BRAKE;}
				break;
			}
			
			case MOTOR_FAST_UP:
			{
				if((pos.target + T2) < m->pos) {m->controlState = MOTOR_FAST_DN;}
				else if(pos.target < (m->pos + m->dist + T2)) {m->posTrg = pos.target;  m->controlState = MOTOR_SLOW_UP;}
				break;
			}
			
			case MOTOR_FAST_DN:
			{
				if((pos.target - T2) > m->pos) {m->controlState = MOTOR_FAST_UP;}
				else if(pos.target > (m->pos - m->dist - T2)) {m->posTrg = pos.target;  m->controlState = MOTOR_SLOW_DN;}
				break;
			}
		}
		
		switch(m->controlState)
		{
	
			case MOTOR_STOP:
			{
				m->speCmd = 0;
				m->speInc_x1024 = 30000;
				break;
			}
			
			case MOTOR_BRAKE:
			{
				m->speCmd = 0;
				m->speInc_x1024 = 30000;
				break;
			}
			
			case MOTOR_SLOW_UP:
			{
				m->speCmd = SLOW;
				int32_t acc_cal = PCTL_accmin(acc);
				m->speInc_x1024 = m1.spetar * 1024 / acc_cal;
				break;
			}
			
			case MOTOR_SLOW_DN:
			{
				m->speCmd = -SLOW;
				int32_t acc_cal = PCTL_accmin(acc);
				m->speInc_x1024 = m1.spetar * 1024 / acc_cal;
				break;
			}
			
			case MOTOR_FAST_UP:
			{
				m->speCmd = constrain(m1.spetar, SLOW, 1900);
				int32_t acc_cal = PCTL_accmin(acc);
				m->speInc_x1024 = m1.spetar * 1024 / acc_cal;
				break;
			}
			
			case MOTOR_FAST_DN:
			{
				m->speCmd = -constrain(m1.spetar, SLOW, 1900);
				int32_t acc_cal = PCTL_accmin(acc);
				m->speInc_x1024 = m1.spetar * 1024 / acc_cal;
				break;
			}
		}

		m->motor_en = 1;
	
}
void tim1_break_protect(m_t* m)
{
    if ((TIM1->SR & TIM_SR_BIF) || (TIM1->SR & TIM_SR_B2IF))
    {
        sys.errBit0 |= ERR_SHORT_CIRCUIT;

        __HAL_TIM_MOE_DISABLE(&htim1);
        TIM1->CCER &= ~m->ccerMask;
        m->motor_en = 0;

        __HAL_TIM_CLEAR_FLAG(&htim1, TIM_FLAG_BREAK);
        __HAL_TIM_CLEAR_FLAG(&htim1, TIM_FLAG_BREAK2);
    }

    static uint32_t release_ts = 0;

    sys.bk_ok  = (HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_12) == GPIO_PIN_SET);
    sys.bk2_ok = (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_11) == GPIO_PIN_SET);

    if (ics.clr == GPIO_PIN_RESET && sys.bk_ok && sys.bk2_ok)
    {
        if (release_ts == 0) release_ts = HAL_GetTick();
        if (HAL_GetTick() - release_ts >= 10)
        {
            uint32_t ccr = *m->arr / 2;
            *m->ccra = ccr;
            *m->ccrb = ccr;

            TIM1->CCER = 0;

            __HAL_TIM_CLEAR_FLAG(&htim1, TIM_FLAG_BREAK);
            __HAL_TIM_CLEAR_FLAG(&htim1, TIM_FLAG_BREAK2);

            TIM1->BDTR |= TIM_BDTR_MOE;
            TIM1->CCER |= m->ccerMask;

            m->motor_en = 1;

            release_ts = 0;
        }
    }
    else
    {
        release_ts = 0;
    }
}

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
    if (htim == &htim16)
    {
        switch (rc.state)
        {
            case 0: // rising trigger
                __HAL_TIM_SetCounter(&htim16, 0);
                __HAL_TIM_SET_CAPTUREPOLARITY(&htim16, TIM_CHANNEL_1, TIM_INPUTCHANNELPOLARITY_FALLING);
                rc.state = 1;
                break;

            case 1: // falling trigger
                rc.cnt1 = __HAL_TIM_GetCounter(&htim16);
                __HAL_TIM_SET_CAPTUREPOLARITY(&htim16, TIM_CHANNEL_1, TIM_INPUTCHANNELPOLARITY_RISING);
                rc.state = 2;
                break;

            case 2: // next trigger
                rc.cnt2 = __HAL_TIM_GetCounter(&htim16);
								if (rc.cnt2 == 0) 
								{
									rc.frequency  = 0;
									rc.duty_cycle = 0;
									rc.control    = 0;     // 無效 → 不控制
									rc.state      = 0;
									break;
								}
                rc.frequency = 1000000 / rc.cnt2;
                rc.duty_cycle = rc.cnt1 * 100 / rc.cnt2;
								m1.rcAvg = filterLp(&m1.rc_flt, rc.cnt1);

								if(m1.rcAvg <900 || m1.rcAvg >2100) // < 0.9ms or > 2.1ms no control
								{
									rc.control = 0;
								}
								else if(m1.rcAvg >= 900 && m1.rcAvg <= 1000) // > 0.9ms and <= 1ms down limit
								{
									rc.control = 0;
								}
								else if(m1.rcAvg > 1000 && m1.rcAvg <= 1999) // software process
								{
									rc.control = ((m1.rcAvg - 1000) * 4095) / 1000;
								}
								else if(m1.rcAvg >= 2000) // >= 2ms up limit
								{
									rc.control = 4095;
								}
								else
								{
									rc.control = 0;
								}
								rc.last_tick = HAL_GetTick();
                rc.state = 0;
								HAL_TIM_IC_Start_IT(&htim16, TIM_CHANNEL_1);//1KHz
                break;
        }
        HAL_TIM_IC_Start_IT(&htim16, TIM_CHANNEL_1);//1KHz
    }
}
void detect_input_mode(m_t* m)
{
		m->vc_x1000 = adc.vc * 10000 / 4095;	// 0 - 10V
		m->ic_x1000 = adc.ic * 20000 / 4095;	// 4 - 20mA
		m->rc_x1000 = rc.control * 1000 / 4095; // 1 - 2ms

		int vc_present = (m->vc_x1000 >= 400) ? 1 : 0;
		int ic_present = (m->ic_x1000 >= 300) ? 1 : 0;
		int rc_present = (rc.control > 1) ? 1 : 0;

		has_vc = vc_present;
		has_ic = ic_present;
		has_rc = rc_present;	

		op.inputmodeCNT = vc_present + ic_present + rc_present;

		if (op.inputmodeCNT >= 2)
		{
				if (sys.inputmodetime == 0){sys.inputmodetime = HAL_GetTick();}

				if ((HAL_GetTick() - sys.inputmodetime) >= 1000)
				{
						sys.errBit1 |= ERR_INPUTMODE;
						modestate  = mode_none;
						mode_value = 0;
				}
		}
		else
		{
				sys.inputmodetime = 0; 
		}

		if (modestate == mode_none && op.inputmodeCNT == 1)
		{
				if (vc_present && !ic_present && !rc_present){modestate = mode_vc;}
				else if (ic_present && !vc_present && !rc_present){modestate = mode_ic;}
				else if (rc_present && !vc_present && !ic_present){modestate = mode_rc;}
		}

		switch(modestate)
		{
				case mode_vc: // 0~10V input
				{				
						if (m->vc_x1000 < 400 || m->vc_x1000 >10100) // vc < 0.4v or vc >10.1v
						{
								mode_value = 0;
								modestate = mode_none;
						} 

						if (m->vc_x1000 < 500 )	// 0.4v <= vc < 0.5v
						{
								mode_value = 0;
						} 
						else if (m->vc_x1000 >= 10000) // vc >= 10v
						{
								mode_value = 1000;
						}
						else 
						{
								mode_value = ((m->vc_x1000 - 500) * 1000) / 9500;        
						}
				}
				break;

				case mode_ic: // 4~20mA input
				{
						if(m->ic_x1000 < 3000 || m->ic_x1000 > 21000)	// ic < 3ma or ic>21ma 
						{
								mode_value = 0;
								modestate = mode_none;
						}
						else if(m->ic_x1000 <= 4000)	// ic <= 4ma
						{
								mode_value = 0;
						}
						else if(m->ic_x1000 >= 20000) // ic >= 20ma
						{
								mode_value = 1000;
						}
						else
						{
								mode_value = ((m->ic_x1000 - 4000) * 1000) / 16000;
						}
				}
				break;

				case mode_rc: // RC input
				{
						mode_value = m->rc_x1000;
						if(HAL_GetTick() - rc.last_tick > 60)
						{
								rc_present = 0;
								modestate = mode_none;
						}
				}	
				break;

				default:
				modestate = mode_none;
				break;
		}
		m->mvAvg = filterLp(&m->mv_flt, mode_value);
}

void check_button_mode_transition(m_t* m)
{
    if(op.button == 1 && last_button_state == 0)
    {
        // 切換到按鍵控制：重置 mode_value 控制
        switch(testmode) 
        {
            case 1: m->curCmd = 0; break;
            case 2: m->speCmd = 0; break;
            case 3: m->speCmd = 0; break;
        }
    }
    else if(op.button == 0 && last_button_state == 1)
    {
        // 切換回 mode_value 控制：重置按鍵控制
        switch(testmode) 
        {
            case 1: m->curCmd = 0; break;
            case 2: m->speCmd = 0; break;
            case 3: m->speCmd = 0; break;
        }
    }

    last_button_state = op.button;
}

uint8_t hallsensor_readraw(m_t* m)
{
		m->hallstate = 0;
    if(HAL_GPIO_ReadPin(HALL_SENSOR_PORTC, HALL_SENSOR_PIN6) == GPIO_PIN_SET){m->hallstate |= 0x01;}
    if(HAL_GPIO_ReadPin(HALL_SENSOR_PORTC, HALL_SENSOR_PIN7) == GPIO_PIN_SET){m->hallstate |= 0x02;}
    return m->hallstate;
}

void hallsensor_update(m_t* m)
{
    if (op.sen_hall == 0)
    {
        return;
    }

    uint8_t raw_state = hallsensor_readraw(m);

    /*
     * Hall debounce 不要太大。
     * 8 對高速 Hall 可能會漏狀態。
     */
    #define HALL_DEB_MAX      2U
    #define HALL_DIR         -1

    static uint8_t deb_cnt = 0;
    static uint8_t last_raw = 0xFF;
    static uint32_t hall_errCount = 0;

    int8_t deltaPos = 0;
    uint8_t valid_transition = 0;

    if (raw_state == last_raw)
    {
        if (deb_cnt < HALL_DEB_MAX)
        {
            deb_cnt++;
        }
    }
    else
    {
        deb_cnt = 0;
        last_raw = raw_state;
        goto hall_speed_counter_update;
    }

    if (deb_cnt < HALL_DEB_MAX)
    {
        goto hall_speed_counter_update;
    }

    m->curstate = raw_state;

    /*
     * 狀態沒變，不更新位置。
     */
    if (m->curstate == m->pvstate)
    {
        goto hall_speed_counter_update;
    }

    /*
     * 正向表：
     * 00 -> 02 -> 03 -> 01 -> 00
     *
     * 反向表：
     * 00 -> 01 -> 03 -> 02 -> 00
     *
     * 目前你的方向已經確認需要 HALL_DIR = -1。
     */
    switch (m->pvstate)
    {
        case 0x00:
        {
            if (m->curstate == 0x02)
            {
                deltaPos =  HALL_DIR;
                valid_transition = 1;
            }
            else if (m->curstate == 0x01)
            {
                deltaPos = -HALL_DIR;
                valid_transition = 1;
            }
        }
        break;

        case 0x02:
        {
            if (m->curstate == 0x03)
            {
                deltaPos =  HALL_DIR;
                valid_transition = 1;
            }
            else if (m->curstate == 0x00)
            {
                deltaPos = -HALL_DIR;
                valid_transition = 1;
            }
        }
        break;

        case 0x03:
        {
            if (m->curstate == 0x01)
            {
                deltaPos =  HALL_DIR;
                valid_transition = 1;
            }
            else if (m->curstate == 0x02)
            {
                deltaPos = -HALL_DIR;
                valid_transition = 1;
            }
        }
        break;

        case 0x01:
        {
            if (m->curstate == 0x00)
            {
                deltaPos =  HALL_DIR;
                valid_transition = 1;
            }
            else if (m->curstate == 0x03)
            {
                deltaPos = -HALL_DIR;
                valid_transition = 1;
            }
        }
        break;

        default:
        {
            m->pvstate = m->curstate;
            goto hall_speed_counter_update;
        }
    }

    if (valid_transition)
    {
        m->hall_pos += deltaPos;

        hall.spe_gap = hall.spe_count;
        if (hall.spe_gap == 0)
        {
            hall.spe_gap = 1;
        }
        hall.spe_count = 0;

        /*
         * 有正常 Hall 轉移，就清除非法跳轉計數。
         */
        hall_errCount = 0;
    }
    else
    {
        /*
         * 非法跳轉：
         * 可能是雜訊，也可能是速度快導致漏掉中間狀態。
         *
         * 這裡只計數，不直接報 ERR_POS_FEEDBACK。
         * 然後同步 pvstate，避免錯誤連續累積。
         */
        if (hall_errCount < 255)
        {
            hall_errCount++;
        }
    }

    /*
     * 不管合法或非法，都同步前一狀態。
     * 避免 pvstate 卡在舊狀態造成連續誤判。
     */
    m->pvstate = m->curstate;

hall_speed_counter_update:

    if (hall.spe_count < 250000)
    {
        hall.spe_count++;
    }

    if (hall.spe_count > hall.spe_gap)
    {
        hall.spe_gap = hall.spe_count;
    }
}
//void hallsensor_update(m_t* m)
//{
//    if (op.sen_hall == 0) return;
//	
//    uint8_t raw_state = hallsensor_readraw(m);

//    static uint8_t deb_cnt = 0;
//    static uint8_t last_raw = 0xFF;

//    if (raw_state == last_raw)
//    {
//        if (deb_cnt < 8)
//        {
//            deb_cnt++;
//            
//            if (deb_cnt == 8)
//            {
//                m->curstate = raw_state;

//                if (m->curstate != m->pvstate)
//                {
//                    if ((m->pvstate == 0x00 && m->curstate == 0x01) || 
//                        (m->pvstate == 0x01 && m->curstate == 0x03) ||
//                        (m->pvstate == 0x03 && m->curstate == 0x02) || 
//                        (m->pvstate == 0x02 && m->curstate == 0x00))
//                    {
//                        m->hall_pos++;
//                        hall.spe_gap = hall.spe_count;
//                        hall.spe_count = 0;
//                    }
//                    else if ((m->pvstate == 0x03 && m->curstate == 0x01) || 
//                             (m->pvstate == 0x01 && m->curstate == 0x00) ||
//                             (m->pvstate == 0x00 && m->curstate == 0x02) || 
//                             (m->pvstate == 0x02 && m->curstate == 0x03))
//                    {
//                        m->hall_pos--;
//                        hall.spe_gap = hall.spe_count;
//                        hall.spe_count = 0;
//                    }
//                    m->pvstate = m->curstate;
//                }
//            }
//        }
//    }
//    else
//    {
//        deb_cnt = 0;
//        last_raw = raw_state;
//    }

//    if(hall.spe_count < 250000) 
//    {
//        hall.spe_count++;
//    }
//    if(hall.spe_count > hall.spe_gap) 
//    {
//        hall.spe_gap = hall.spe_count;
//    }
//}

uint8_t limit_reached(m_t* m)
{
    if (!(op.sen_pot || op.sen_hall)){return 0;}

    ln.cur = constrain(m->curAvg, 0, 10000); 
    uint32_t now = HAL_GetTick();
    
    // 採樣時間窗口 (20ms)
    static uint32_t last_check_time = 0;
    static uint8_t last_result = 0; 
    
    if (now - last_check_time < 20) 
    {
        return last_result; 
    }
    last_check_time = now;

    // 初始化
    if (ln.still_ms == 0)
    {
        ln.still_ms       = now;
        ln.still_delta_ms = 0;
        ln.last_pos       = m->pos;
        ln.dp_pos         = 0;
        ln.run_cur        = 0;
        last_result       = 0; 
        return 0;
    }

    // 計算位移
    ln.dp_pos = m->pos - ln.last_pos;
    ln.last_pos = m->pos; 

    // 【修正 1】標準放寬：只要 20ms 內有走「2步」以上，就重置靜止計時
    // 原本是 > 10，對緩啟動太嚴格了
    if (abs(ln.dp_pos) >= 2)
    {
        ln.still_ms       = now;
        ln.still_delta_ms = 0;

        // 更新運行電流參考值
        if (ln.run_cur == 0) ln.run_cur = ln.cur;
        else ln.run_cur = (ln.run_cur * 3 + ln.cur) / 4;

        last_result = 0; 
        return 0;
    }

    // 累積靜止時間
    ln.still_delta_ms = now - ln.still_ms;
    
    // 判斷時間可以稍微拉長一點點，例如 500ms，避免太快誤判
    if (ln.still_delta_ms < 500)
    {
        last_result = 0; 
        return 0;
    }

    //大電流堵轉
    if (ln.run_cur > 0)
    {
        int32_t big_thr = (ln.run_cur * 3) / 2;
        if (big_thr < 200) big_thr = 200; // 給個底限
        
        if (ln.cur >= big_thr)
        {
             last_result = 1;
             return 1;
        }
    }

    // 若真的超過 500ms 都沒動靜 (dp_pos < 2)，就算電流沒飆高，也視為卡死/到底
    last_result = 1;
    return 1;
}

void learnHandler(m_t* m)
{
    static uint8_t learn_phase = LEARN_FAST_TO_LIMIT;
    static uint8_t last_step = 0xFF;
    static int32_t back_start_pos = 0;
    static int32_t back_target_cnt = 0;
		
		static uint32_t phase_start_time = 0;

    int32_t limit_dir = 0;

    /*
     * learnstep:
     * 0 = 下極限
     * 1 = 上極限
     * 2 = 再次下極限並完成
     */
    switch (ln.learnstep)
    {
        case 0:
        case 2:
            limit_dir = -1;
            break;

        case 1:
            limit_dir = +1;
            break;

        default:
            limit_dir = 0;
            break;
    }

    uint32_t now = HAL_GetTick();

    /*
     * Step 改變時初始化
     */
    if (ln.learnstep != last_step)
    {
        last_step = ln.learnstep;
        learn_phase = LEARN_FAST_TO_LIMIT;

        m->pwm_x1024 = 0;
        m->pwmReq = 0;
        m->speCmd = 0;
        m->speInc_x1024 = 3000;

        ln.spe_target = 0;
        ln.last_ramp_time = 0;
        ln.curtime = 0;
        ln.still_ms = 0;
        ln.still_delta_ms = 0;
        ln.run_cur = 0;
        ln.last_pos = m->pos;

        back_start_pos = m->pos;
        back_target_cnt = 0;
				phase_start_time = now;
    }

    switch (learn_phase)
    {
        case LEARN_FAST_TO_LIMIT:
        {
            /*
             * 第一次快速找極限，只做粗定位，不記錄位置。
             */
            if (ln.spe_target < LEARN_FAST_PWM)
            {
                if (now - ln.last_ramp_time >= 50)
                {
                    ln.spe_target += 50;
                    ln.last_ramp_time = now;

                    if (ln.spe_target > LEARN_FAST_PWM)
                    {
                        ln.spe_target = LEARN_FAST_PWM;
                    }
                }
            }

            m->speCmd = limit_dir * ln.spe_target;

            if (ln.spe_target < LEARN_FAST_PWM || !limit_reached(m))
            {
                ln.curtime = 0;
                return;
            }

            if (ln.curtime == 0)
            {
                ln.curtime = now;
                return;
            }

            if (now - ln.curtime < LEARN_CONFIRM_MS)
            {
                return;
            }

            /*
             * 快速碰到底後，先停止。
             */
            m->speCmd = 0;
            ln.curtime = now;
            learn_phase = LEARN_WAIT_AFTER_FAST;
            return;
        }

        case LEARN_WAIT_AFTER_FAST:
        {
            m->speCmd = 0;

            if ((abs(m->pwmReq) > LEARN_STOP_PWM_TH) ||
                ((now - ln.curtime) < LEARN_WAIT_MS))
            {
                return;
            }

            /*
             * 準備反向退一小段。
             * 下極限確認：先伸出一點，所以方向是 +1。
             * 上極限確認：先縮回一點，所以方向是 -1。
             */
            back_start_pos = m->pos;
            back_target_cnt = (op.sen_hall) ? LEARN_BACK_COUNT_HALL : LEARN_BACK_COUNT_POT;

            ln.still_ms = 0;
            ln.still_delta_ms = 0;
            ln.run_cur = 0;
            ln.last_pos = m->pos;
						
						/*
						 * 退開段重新計時。
						 * 避免 Hall 異常時 moved 一直不到，導致一路退到另一端。
						 */
						phase_start_time = now;
            learn_phase = LEARN_BACK_OFF;
						
						
            return;
        }
				case LEARN_BACK_OFF:
				{
						int32_t back_dir = -limit_dir;
						int32_t moved = abs(m->pos - back_start_pos);

						m->speCmd = back_dir * LEARN_BACK_PWM;

						/*
						 * 正常情況：
						 * Hall/POT 位移達到 back_target_cnt，就停止退開。
						 *
						 * 異常 Hall 波形情況：
						 * 如果 moved 一直不增加，也不能無限退，
						 * 所以加入 LEARN_BACK_MAX_MS 時間保護。
						 */
                        if (moved < back_target_cnt)
                        {
                            if ((now - phase_start_time) < LEARN_BACK_MAX_MS)
                            {
                                return; // Still waiting for actual sensor motion.
                            }
                            // FAIL-SAFE: timeout is evidence of lost feedback,
                            // NOT successful movement to the next phase.
                            ln.error = 1;
                            m->speCmd = 0;
                            m->pwmReq = 0;
                            m->pwm_x1024 = 0;
                            learn_phase = LEARN_FAST_TO_LIMIT;
                            last_step = 0xFF;
                            return; // Caller terminates learning and sets error flags.
                        }

						m->speCmd = 0;
						ln.curtime = now;
						learn_phase = LEARN_WAIT_AFTER_BACK;
						return;
				}
//        case LEARN_BACK_OFF:
//        {
//            int32_t back_dir = -limit_dir;
//            int32_t moved = abs(m->pos - back_start_pos);

//            m->speCmd = back_dir * LEARN_BACK_PWM;

//            /*
//             * 退開一小段即可。
//             * 這裡不要用 limit_reached()，避免剛離開極限時誤判。
//             */
//            if (moved < back_target_cnt)
//            {
//                return;
//            }

//            m->speCmd = 0;
//            ln.curtime = now;
//            learn_phase = LEARN_WAIT_AFTER_BACK;
//            return;
//        }

        case LEARN_WAIT_AFTER_BACK:
        {
            m->speCmd = 0;

            if ((abs(m->pwmReq) > LEARN_STOP_PWM_TH) ||
                ((now - ln.curtime) < LEARN_WAIT_MS))
            {
                return;
            }

            /*
             * 準備慢速重新靠近極限。
             * 重新初始化 limit_reached() 需要用到的靜止判斷基準。
             */
            ln.still_ms = 0;
            ln.still_delta_ms = 0;
            ln.run_cur = 0;
            ln.last_pos = m->pos;
            ln.curtime = 0;

            learn_phase = LEARN_SLOW_TO_LIMIT;
            return;
        }

        case LEARN_SLOW_TO_LIMIT:
        {
            /*
             * 慢速靠近極限，這一次才是真正要記錄的位置。
             */
            m->speCmd = limit_dir * LEARN_SLOW_PWM;

            if (!limit_reached(m))
            {
                ln.curtime = 0;
                return;
            }

            if (ln.curtime == 0)
            {
                ln.curtime = now;
                return;
            }

            if (now - ln.curtime < LEARN_CONFIRM_MS)
            {
                return;
            }

            m->speCmd = 0;
            ln.curtime = now;
            learn_phase = LEARN_WAIT_AFTER_SLOW;
            return;
        }

        case LEARN_WAIT_AFTER_SLOW:
        {
            m->speCmd = 0;

            if ((abs(m->pwmReq) > LEARN_STOP_PWM_TH) ||
                ((now - ln.curtime) < LEARN_WAIT_MS))
            {
                return;
            }

            /*
             * 慢速確認後，才記錄真正極限位置。
             */
            switch (ln.learnstep)
            {
                case 0:
                    ln.pos_min = m->pos;
                    ln.learnstep = 1;
                    break;

                case 1:
                    // IMPORTANT: positive stroke direction is an assumption of
                    // the existing pos_soft()/pos_memory() implementation.
                    // Confirm Hall/POT polarity at the bench before release.
                    if (m->pos <= ln.pos_min || (m->pos - ln.pos_min) < 50)
                    {
                        ln.error = 1; // No credible full-travel feedback.
                    }
                    else
                    {
                        ln.pos_max = m->pos;
                        ln.learnstep = 2;
                    }
                    break;

                case 2:
                    /*
                     * Final gate: traveled a valid positive stroke AND returned
                     * close to the previously confirmed lower endpoint.
                     * 5% (min 20 counts) is an INITIAL REVIEW VALUE ONLY.
                     * Calibrate separately for Hall/POT and each actuator family.
                     */
                    {
                        int32_t stroke = ln.pos_max - ln.pos_min;
                        int32_t endpoint_diff = abs(m->pos - ln.pos_min);
                        int32_t tolerance = stroke / 20;
                        if (tolerance < 20) tolerance = 20;
                        if (stroke < 50 || endpoint_diff > tolerance)
                        {
                            ln.error = 1;
                            break;
                        }
                    }
                    ln.pos_min = m->pos;

                    pos_soft();
                    testmode = 3;
                    go_home_after_learn = 1;
                    ln.learningmode = 0;
                    ln.learnstep = 0;
                    ln.curtime = 0;
                    ln.learnstarttime = 0;
                    PCTL.ln_mode = 0x02;
                    pos.need_learn = 0;
                    sys.errBit0 &= ~ERR_POS_FEEDBACK;
                    break;

                default:
                    ln.error = 1;
                    break;
            }

            m->pwm_x1024 = 0;
            m->pwmReq = 0;
            m->speCmd = 0;

            ln.spe_target = 0;
            ln.curtime = 0;
            ln.still_ms = 0;
            ln.still_delta_ms = 0;
            ln.run_cur = 0;

            learn_phase = LEARN_FAST_TO_LIMIT;
            last_step = 0xFF;
            return;
        }

        default:
        {
            m->speCmd = 0;
            learn_phase = LEARN_FAST_TO_LIMIT;
            last_step = 0xFF;
            ln.error = 1;
            return;
        }
    }
}


void config_sensor_gpio(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();

    /*
     * op.sensormode == 0 : Hall
     * op.sensormode == 1 : Potentiometer
     */
    if (op.sensormode == 0)
    {
        /*
         * Hall mode:
         * PC6 / PC7 是真正 Hall A/B 數位輸入腳。
         * 建議兩支都開 pull-up。
         */
        GPIO_InitStruct.Pin   = GPIO_PIN_6 | GPIO_PIN_7;
        GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
        GPIO_InitStruct.Pull  = GPIO_PULLUP;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
        HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

				GPIO_InitStruct.Pin   = GPIO_PIN_11;
				GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
				GPIO_InitStruct.Pull  = GPIO_PULLUP;
				GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
				HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    }
    else
    {
        /*
         * Pot mode:
         * PC6 / PC7 不作 Hall 計數，避免內部上拉影響外部共用線。
         */
        GPIO_InitStruct.Pin   = GPIO_PIN_6 | GPIO_PIN_7;
        GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
        GPIO_InitStruct.Pull  = GPIO_NOPULL;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
        HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

        /*
         * PB11 回到 ADC_IN15。
         * POT 模式一定要 Analog + No Pull，
         * 不然會影響 POT ADC 讀值。
         */
        GPIO_InitStruct.Pin   = GPIO_PIN_11;
        GPIO_InitStruct.Mode  = GPIO_MODE_ANALOG;
        GPIO_InitStruct.Pull  = GPIO_NOPULL;
        GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
        HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
    }
}


int arbitrate_control_source(void)
{
		if (go_home_after_learn) 
		{
        g_active_src = SRC_home;
        return 1;
    }
    // 計算輸入種數（UART / 手控器 / 三種輸入）
    op.controlmodeCNT = (has_uart ? 1:0) + (has_hand ? 1:0) + (has_rc ? 1:0) + (has_vc ? 1:0) + (has_ic ? 1:0);

    if (op.controlmodeCNT == 0) 
		{
        g_active_src = SRC_none;
        return 1;
    }
    if (op.controlmodeCNT >= 2) 
		{
        // 輸入衝突 → 丟錯誤碼
        sys.errBit0 |= ERR_CONTROL_MODE;

        g_active_src = SRC_none;
        m1.speCmd = 0;
        m1.curCmd = 0;
        m1.mvAvg = 0;
        return 0;
    }

    // 只有一個輸入 → 依優先序選定
    if (has_uart)      g_active_src = SRC_uart;
    else if (has_hand) g_active_src = SRC_hand;
    else if (has_rc)   g_active_src = SRC_rc;
    else if (has_vc)   g_active_src = SRC_vc;
    else if (has_ic)   g_active_src = SRC_ic;
    else               g_active_src = SRC_none;

    return 1;
}

void control_source_selection(void)
{
    switch (g_active_src)
    {
				case SRC_home:
						op.button = 0; 
						op.tool   = 0;
						break;
        case SRC_uart:
            // PC Tool
            op.button = 0; op.tool = 1;
						go_home_after_learn = 0;
            // position_control() 會用 PCTL.pos_pct 轉成 pos.target
            break;

        case SRC_hand:
            // 手控器
            op.button = 0; op.tool = 0;
						go_home_after_learn = 0;
            break;

        case SRC_rc:
            // 輸入(PWM)模式
            op.button = 1;
						go_home_after_learn = 0;				
            modestate = mode_rc;
            break;

        case SRC_vc:
						// 輸入(電壓)模式
            op.button = 1;
						go_home_after_learn = 0;				
            modestate = mode_vc;
            break;

        case SRC_ic:
						// 輸入(電流)模式
            op.button = 1;
						go_home_after_learn = 0;				
            modestate = mode_ic;
            break;

        case SRC_none:
        default:
            // 無輸入
            op.button = 0; op.tool = 0;
            m1.speCmd = 0; m1.curCmd = 0;
            break;
    }
}

void uart_par(void)
{
		PCTL_setting();
    if(PCTL.set_mode == 0x00) 
		{
        PCTL.pos_ctlmode = 0x00;
    }
		if(PCTL.MP == 0x02) 
		{
				PCTL_factory();
				PCTL.MP = 0x00;
				return;
		}
		if(PCTL.error_clr == 0x02)
		{
				sys.clearRequest = 1;
				PCTL.error_clr = 0x00;
		}
		if(PCTL.error_clr == 0x03)
		{
				sys.MotorCNT = 0;
				PCTL.error_clr = 0x00;
		}
		
		//RD
		m1.dp_curAvg = filterLp(&m1.dp_cur_flt, m1.cur);
		m1.dp_curAvg = constrain(m1.dp_curAvg, -10000, 10000);
		PCTL.dp_cur = abs(m1.dp_curAvg) / 10;
		PCTL.dp_cur = constrain(PCTL.dp_cur, 0, 1000);
		PCTL.dp_pos = pos.dp_pos;
		PCTL.dp_pos = constrain(PCTL.dp_pos, 0, 1000);
		if(PCTL.set_mode == 0x01){sys.Status = 0x01;}
		else{sys.Status = 0x00;}
		if(op.sen_hall){sys.SensorStatus = 0x01;}
		if(op.sen_pot){sys.SensorStatus = 0x02;}
		
		//CNT
		uint8_t VoltErr = (sys.errBit0 & (ERR_VOLT_HIGH | ERR_VOLT_LOW | ERR_BRAKE_OVERLOAD)) != 0u; // high / low vlotage and brake resistor
		uint8_t CurErr  = (sys.errBit0 & (ERR_CUR_LIMIT | ERR_SHORT_CIRCUIT)) != 0u; // current short and overload 
		uint8_t PosErr  = (sys.errBit0 & (ERR_POS_FEEDBACK | ERR_LEARN_FAIL | ERR_CONTROL_MODE)) != 0u ||(sys.errBit1 & ERR_INPUTMODE) != 0u; // position related and control mode
		uint8_t ErrCode = (sys.errBit0 | sys.errBit1) != 0u;	// errorflag total

		CNTonce(VoltErr, &exVoltErr, &sys.VoltErrCNT);
		CNTonce(CurErr,  &exCurErr,  &sys.CurErrCNT);
		CNTonce(PosErr,  &exPosErr,  &sys.PosErrCNT);
		CNTonce(ErrCode, &exErrCode, &sys.ErrCodeCNT);
}

uint8_t presscontrol(press_t *pt, uint8_t expected_cmd, uint8_t cur_cmd, uint8_t keyTrg, uint32_t now_ms)
{
    if (!keyTrg) 
		{
        if (pt->count && (now_ms - pt->last_ms > pt->gap_ms)) 
				{
            pt->count = 0;
        }
        return 0;
    }
    if (cur_cmd != expected_cmd) 
		{
        pt->count = 0;
        pt->last_ms = 0;
        return 0;
    }
    if (pt->count == 0 || (now_ms - pt->last_ms) <= pt->gap_ms) {
        pt->count++;
    } else {
        pt->count = 1;
    }
    pt->last_ms = now_ms;

    if (pt->count >= pt->need) {
        pt->count = 0;      
        pt->last_ms = 0;
        return 1;
    }
    return 0;
}

void PCTL_setting(void)
{
		 // --- Sensor mode ---
    if (PCTL.sensor_mode == 0x01) { op.sensormode = 0; } // Hall
    else if (PCTL.sensor_mode == 0x02) { op.sensormode = 1; } // Pot
		
    if (last_sensor_mode == 0xFF)
    {
        last_sensor_mode = op.sensormode;
    }
    else if (op.sensormode != last_sensor_mode)
    {
        pos.need_learn = 1;
        pos.decided    = 0;
        testmode       = 2; 
        sys.errBit0   |= ERR_POS_FEEDBACK;

        pos.min        = 0;
        pos.max        = 0;
        pos.softstroke = 0;
        pos.hardstroke = 0;
        ln.pos_min     = 0;
        ln.pos_max     = 0;
    }
    last_sensor_mode = op.sensormode;
		
    // --- Voltage window / Brake ---
    sys.vbushigh = constrain(PCTL.vbus_high, 0, 500);
    sys.vbuslow  = constrain(PCTL.vbus_low,  0, 500);
    sys.brakeOn  = constrain(PCTL.v_brakeOn, 110, 520);	// 出廠設定為52V(默認關閉)
    sys.brakeOff = constrain(PCTL.v_brakeOff,100, 510);	// 出廠設定為51V(默認開啟)

    // --- Current limits ---
//    m1.setcur         = constrain(PCTL.cur_limited * 10, 0, 10000);
//    m1.cur_overload   = constrain(PCTL.cur_overload * 10, 0, 10000);
//    m1.cur_ot_set     = constrain(PCTL.cur_overload_time, 0, 5000);
		m1.setcur       = constrain(PCTL.cur_limited  * 10, 30, 10000);
    m1.cur_overload = constrain(PCTL.cur_overload * 10, 30, 10000);
//    if (m1.cur_overload > (m1.setcur * 9) / 10)
//    {
//        m1.cur_overload = (m1.setcur * 9) / 10;   // 過流門檻至少比限流低 10%
//    }

    m1.cur_ot_set   = constrain(PCTL.cur_overload_time, 0, 5000);

    // --- Speed and ramps ---
    sys.speset        = constrain(PCTL.spe_pct / 10, 0, 100);

    // --- Position targets & soft-stroke ---
		pos.acc_x200  = constrain(PCTL.soft_acc_pct, 0, 200);
		pos.setmax    = constrain(PCTL.soft_max_pct / 10, 0, 100);
		pos.setmin    = constrain(PCTL.soft_min_pct / 10, 0, 100);

		if(pos.setmax < pos.setmin)
		{
				int32_t tmp = pos.setmax;
				pos.setmax = pos.setmin;
				pos.setmin = tmp;
		}

		m1.posCmd = constrain(PCTL.pos_pct / 10, pos.setmin, pos.setmax);
		if (m1.controlState == MOTOR_FAST_UP){acc = PCTL_accmin(PCTL.ext_acc_ms);
		}
		else if (m1.controlState == MOTOR_SLOW_UP){acc = PCTL_accmin(PCTL.ext_dec_ms);}
		else if (m1.controlState == MOTOR_FAST_DN){acc = PCTL_accmin(PCTL.ret_acc_ms);}
		else if (m1.controlState == MOTOR_SLOW_DN){acc = PCTL_accmin(PCTL.ret_dec_ms);}
		else{acc = PCTL_accmin(PCTL.ext_acc_ms);}
    pos_soft();
}

void motorstatus(void)
{
		if(ln.learningmode == 2)
		{
				sys.MotorStatus = 0x5;
		}	
		else if(ics.pos_ok == 1)
		{
				if(abs(pos.max - pos.target) <= pos.acc)
				{
						sys.MotorStatus = 0x07;
				}
				else if(abs(pos.min - pos.target) <= pos.acc)
				{
						sys.MotorStatus = 0x06;
				}
				else
				{
						sys.MotorStatus = 0x04;
				}
		}
		else if (m1.controlState == MOTOR_FAST_UP || m1.controlState == MOTOR_SLOW_UP)
		{
				sys.MotorStatus = 0x02;
		}
		else if (m1.controlState == MOTOR_FAST_DN || m1.controlState == MOTOR_SLOW_DN)
		{
				sys.MotorStatus = 0x03;
		}
//		else if(ln.error || pos.need_learn || m1.spetar <= 0 || (sys.errBit0 != 0u) || (sys.errBit1 != 0u) || m1.controlState == MOTOR_STOP)
		else
    {
        sys.MotorStatus = 0x01;
    }
}

void PCTL_factory_24V_default(void)
{
    /*
     * 第一次燒錄 / Flash 空白時使用。
     * 不依賴 sys.vbus，避免剛開機 VBUS 尚未穩定，
     * 被誤判成 sys.vbus < 180 的 12V 組。
     */

    PCTL.vbus_high         = 310;
    PCTL.vbus_low          = 190;
    PCTL.v_brakeOn         = 520;
    PCTL.v_brakeOff        = 510;

    PCTL.cur_limited       = 350;     // 單位 10mA = 3500mA
    PCTL.cur_overload      = 270;     // 單位 10mA = 2700mA
    PCTL.cur_overload_time = 500;     // ms

    PCTL.spe_pct           = 1000;    // 100.0%
    PCTL.ext_acc_ms        = 1000;
    PCTL.ext_dec_ms        = 1000;
    PCTL.ret_acc_ms        = 1000;
    PCTL.ret_dec_ms        = 1000;

    PCTL.pos_pct           = 0;
    PCTL.soft_acc_pct      = 10;
    PCTL.soft_max_pct      = 1000;
    PCTL.soft_min_pct      = 0;

    PCTL.sensor_mode       = 0x01;    // 0x01=HALL, 0x02=POT

    PCTL.ln_mode           = 0x00;
    PCTL.error_clr         = 0x00;

    PCTL.MP                = 0x00;
}

void PCTL_factory(void)
{
		
		if(sys.vbus < 180)
		{			
				PCTL.vbus_high         = 160;
				PCTL.vbus_low          = 110;
				PCTL.v_brakeOn         = 520;
				PCTL.v_brakeOff        = 510;

				PCTL.cur_limited       = 50;     			// 單位 10mA
				PCTL.cur_overload      = 40;      		// 單位 10mA
				PCTL.cur_overload_time = 500;  			 	// 0~5000 ms

				PCTL.spe_pct           = 1000;       	// 0~1000 → /10 = %
				PCTL.ext_acc_ms        = 1000;
				PCTL.ext_dec_ms        = 1000;
				PCTL.ret_acc_ms        = 1000;
				PCTL.ret_dec_ms        = 1000;

				PCTL.pos_pct           = 0;           // 目標位置預設 0%（PC Tool可改）
				PCTL.soft_acc_pct      = 10;     			// 0~200 → 0~20%
				PCTL.soft_max_pct      = 1000;      		// 90.0%（0~1000）
				PCTL.soft_min_pct      = 0;      		// 10.0%（0~1000）

				PCTL.sensor_mode       = 0x02;        // 0x01=HALL, 0x02=POT

				PCTL.ln_mode           = 0x00;
				PCTL.error_clr         = 0x00;

				// 初始化完成
				PCTL.MP = 0x00;
		}
		if(sys.vbus < 280 && sys.vbus >180)
		{			
				PCTL.vbus_high         = 310;
				PCTL.vbus_low          = 190;
				PCTL.v_brakeOn         = 520;
				PCTL.v_brakeOff        = 510;

				PCTL.cur_limited       = 350;     		// 單位 10mA
				PCTL.cur_overload      = 270;      		// 單位 10mA
				PCTL.cur_overload_time = 500;  				// 0~5000 ms

				PCTL.spe_pct           = 1000;       	// 0~1000 → /10 = %
				PCTL.ext_acc_ms        = 1000;
				PCTL.ext_dec_ms        = 1000;
				PCTL.ret_acc_ms        = 1000;
				PCTL.ret_dec_ms        = 1000;

				PCTL.pos_pct           = 0;           // 目標位置預設 0%（PC Tool可改）
				PCTL.soft_acc_pct      = 10;     			// 0~200 → 0~20%
				PCTL.soft_max_pct      = 1000;      		// 90.0%（0~1000）
				PCTL.soft_min_pct      = 0;      		// 10.0%（0~1000）

				PCTL.sensor_mode       = 0x01;        // 0x01=HALL, 0x02=POT

				PCTL.ln_mode           = 0x00;
				PCTL.error_clr         = 0x00;

				// 初始化完成
				PCTL.MP = 0x00;
		}
		if(sys.vbus < 380 && sys.vbus >280)
		{			
				PCTL.vbus_high         = 400;
				PCTL.vbus_low          = 330;
				PCTL.v_brakeOn         = 520;
				PCTL.v_brakeOff        = 510;

				PCTL.cur_limited       = 250;     		// 單位 10mA
				PCTL.cur_overload      = 200;      		// 單位 10mA
				PCTL.cur_overload_time = 500;  				// 0~5000 ms

				PCTL.spe_pct           = 1000;       	// 0~1000 → /10 = %
				PCTL.ext_acc_ms        = 1000;
				PCTL.ext_dec_ms        = 1000;
				PCTL.ret_acc_ms        = 1000;
				PCTL.ret_dec_ms        = 1000;

				PCTL.pos_pct           = 0;           // 目標位置預設 0%（PC Tool可改）
				PCTL.soft_acc_pct      = 10;     			// 0~200 → 0~20%
				PCTL.soft_max_pct      = 1000;      		// 90.0%（0~1000）
				PCTL.soft_min_pct      = 0;      		// 10.0%（0~1000）

				PCTL.sensor_mode       = 0x01;        // 0x01=HALL, 0x02=POT

				PCTL.ln_mode           = 0x00;
				PCTL.error_clr         = 0x00;

				// 初始化完成
				PCTL.MP = 0x00;
		}
		if(sys.vbus < 500 && sys.vbus >380)
		{			
				PCTL.vbus_high         = 500;
				PCTL.vbus_low          = 450;
				PCTL.v_brakeOn         = 520;
				PCTL.v_brakeOff        = 510;

				PCTL.cur_limited       = 150;     		// 單位 10mA
				PCTL.cur_overload      = 120;      		// 單位 10mA
				PCTL.cur_overload_time = 500;  				// 0~5000 ms

				PCTL.spe_pct           = 1000;       	// 0~1000 → /10 = %
				PCTL.ext_acc_ms        = 1000;
				PCTL.ext_dec_ms        = 1000;
				PCTL.ret_acc_ms        = 1000;
				PCTL.ret_dec_ms        = 1000;

				PCTL.pos_pct           = 0;           // 目標位置預設 0%（PC Tool可改）
				PCTL.soft_acc_pct      = 10;     			// 0~200 → 0~20%
				PCTL.soft_max_pct      = 1000;      		// 90.0%（0~1000）
				PCTL.soft_min_pct      = 0;      		// 10.0%（0~1000）

				PCTL.sensor_mode       = 0x01;        // 0x01=HALL, 0x02=POT

				PCTL.ln_mode           = 0x00;
				PCTL.error_clr         = 0x00;

				// 初始化完成
				PCTL.MP = 0x00;
		}		

}
void pos_memory(void)
{
    // 只在上電後執行一次
    if (pos.decided) 
    {
        return;
    }
    pos.decided = 1;

    pos.need_learn = 1;
    testmode       = 2;
    sys.errBit0   |= ERR_POS_FEEDBACK;
		
    // check ln.pos_min / ln.pos_max
    int32_t hardstroke = ln.pos_max - ln.pos_min;
    if (hardstroke < 0) hardstroke = -hardstroke;

    if (ln.pos_max == ln.pos_min || hardstroke < 50)
    {
        return;
    }
		// check last_pos
    int32_t last_pos = 0;
    if (op.sensormode == 0) // Hall
    {
        last_pos = pos.last_hall_pos;
    }
    else                    // Pot
    {
        last_pos = pos.last_pot_pos;
    }
		
    if (last_pos == 0)
    {
        return;
    }

    // check last_pos between ln.pos_min or ln.pos_max
    int32_t margin = hardstroke / 20; // 預設用 5%
    if (margin < 20) margin = 20;

    if (last_pos < (ln.pos_min - margin) || last_pos > (ln.pos_max + margin))
    {
        return;
    }
		
    if (op.sensormode == 0) // Hall
    {
        m1.hall_pos = last_pos;
    }
    else                    // Pot
    {
        m1.potAvg = last_pos;
    }

    pos_soft();

		// check pos.max and pos.min
    if (pos.max <= pos.min || (pos.softstroke <= 50))
    {
        return;
    }

    pos.need_learn = 0;
    testmode = 3;
    sys.errBit0 &= ~ERR_POS_FEEDBACK;
}

void motor_time(void)
{
		m1.motor_now_pos = m1.pos;
		m1.motor_delta_pos = m1.motor_now_pos - m1.motor_last_pos;
		m1.motor_last_pos = m1.motor_now_pos;
		
		if(ln.learningmode == 2 && ln.error == 0 && abs(m1.motor_delta_pos) >= 3)
		{
				ln.learning_mov = 1;
		}
		else
		{
				ln.learning_mov = 0;
		}
		
		if((m1.controlState == MOTOR_FAST_UP) || (m1.controlState == MOTOR_FAST_DN) || (m1.controlState == MOTOR_SLOW_UP) || (m1.controlState == MOTOR_SLOW_DN) || ln.learning_mov == 1)
		{
				m1.motor_mov = 1;
		}
		else
		{
				m1.motor_mov = 0;
		}
		if(testmode == 2 && (cmd == 0x01 || cmd == 0x02))
		{
				m1.motor_mov = 1;
		}
		
		uint32_t motor_clk = HAL_GetTick();
		if(m1.motor_prev_ms == 0)
		{
				m1.motor_prev_ms = motor_clk;
		}
		uint32_t motor_dt = motor_clk - m1.motor_prev_ms;
		m1.motor_prev_ms = motor_clk;
		if(m1.motor_mov)
		{
				m1.motor_acc_ms += motor_dt;
				if(m1.motor_acc_ms >= 1000)
				{
						m1.motor_acc_ms -= 1000;
						sys.MotorCNT++;
				}
		}
}


