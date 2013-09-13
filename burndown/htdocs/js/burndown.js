$(document).ready(function(){

  // Request burn down chart data via Ajax
  // Use the default metric set in burndown admin panel
  if (render_burndown == true) {
    show_spinner("#chart1");
    $.ajax({
      type: 'GET',
      data: {'milestone':milestone_name},
      url: base_url + '/ajax/burndown/',
      success: function(data, textStatus, jqXHR) {
        if (data['result'] == 'no-data') {
          burndown_fail();
        }
        else {
          $("#chart1").html("");
          draw_burndown(data);
        }
      },
      error: function(data, textStatus, jqXHR) {
        $burndown_fail();
      }
    });
  }
  else if (render_burndown == 'false') {
    $("#chart1").html("<span class='block center'> To generate a burn down \
                      chart for this milestone, please set the start and due \
                      date.</span>")
                .attr("class", "box-info");
  }

  // Redraw the burn down if the user changes the metric
  $('#tickets-metric, #hours-metric, #points-metric').click(function() {
    show_spinner("#chart1");
    $("#burndown-spinner").css("margin-top", "100px");
    metric_value = this.id.split('-')[0];
    $.ajax({
      type: 'GET',
      data: {'metric':metric_value, 'milestone':milestone_name},
      url: base_url +'/ajax/burndown/',
      success: function (data) {
        remove_spinner("#chart1")
        if (data['result'] != 'no-data') {
          redraw_burndown(data, metric_value);
        }
        else {
          burndown_fail();
        }
      },
      error: function(data, textStatus, jqXHR) {
        remove_spinner("#chart1")
        burndown_fail();
      }
    });
  });

  function draw_burndown(data) {
    // Expects date as a string in yyyy-mm-dd format, with a time added for 
    // greater accuracy.
    window.addTime = function(date){
      var formatted_date = date + ' 12:01AM';
      return formatted_date
    };

    // Function which returns a two dimensional array. Each array has a 
    // date and value, with the value reflecting some kind of work either 
    // remaining or completed on that day
    window.dataSeries = function(curvedata){
      var series_data = [];
      for (var i=0; i < curvedata.length; i++) {
        series_data.push([addTime(curvedata[i][0]), curvedata[i][1]]);
      }
      return series_data;
    };

    // Curve data needed for jqPlot series
    var burndowncurve = dataSeries(data['burndowndata']);
    var teameffortcurve = dataSeries(data['teameffortdata']);
    var idealcurve = dataSeries(data['idealcurvedata']);
    var addedcurve = dataSeries(data['workaddeddata']);

    // Makes the jqPlot resize when the window dimensions change
    $(window).on('debouncedresize', function() {
          plot1.replot( { resetAxes: true } );
    });

    // Calculate the interval between x-axis dates (aka tickInterval)
    // 20 ticks is about right on a average sized screen
    // We plus one so that for 0.x numbers, we still get a 1 day interval
    tick_gap = Number(String((idealcurve.length / 20)));
    if (tick_gap < 1) {
      xaxis_interval = '1 day';
    }
    else {
      xaxis_interval = String(tick_gap + 1).split('.')[0] + ' days';
    }

    // Render the jqPlot burn down chart
    window.plot1 = $.jqplot('chart1', [idealcurve, burndowncurve, teameffortcurve, addedcurve], {
      gridPadding: {top:28},
      animate: true,
      animateReplot: true,
      grid: {
        shadow: false,
        background: '#FFFFFF'
      },
      axesDefaults: {
        tickRenderer: $.jqplot.CanvasAxisTickRenderer,
        tickOptions: {
          fontFamily: 'Open Sans',
          fontSize: '8pt'
        },
        labelOptions: {
          textColor: '#0066CC',
          fontFamily: 'Open Sans',
          fontSize: '10pt',
          fontWeight: 'normal'
        }
      },
      axes: {
        xaxis: {
          renderer:$.jqplot.DateAxisRenderer,
          tickOptions:{formatString: '%d %b'},
          label: 'Days in Milestone',
          tickInterval:xaxis_interval,
          min: data['start_date'],
          max: data['end_date']
        },
        yaxis: {
          label: 'Effort (' + data['effort_units'] +')',
          min: 0,
          labelRenderer: $.jqplot.CanvasAxisLabelRenderer
        }
      },
      highlighter: {
        show: true,
        tooltipAxes: 'both',
        sizeAdjust: 7.5,
        fadeTooltip: true,
        tooltipFadeSpeed: 'fast',
        tooltipAxes: 'xy',
        formatString: '%s - %s ' + data['effort_units']
        },
      series:[
              {
                label: 'Ideal effort',
                color:'#AAA',
                showMarker: false,
                linePattern: 'dashed',
                lineWidth: 1.25,
                shadow: false
              },
              {
                color:'#23932C',
                label: 'Remaining effort',
                showMarker: false,
                shadow: false
              },
              {
                label:'Team effort',
                showMarker: false,
                color: '#FFD600',
                shadow: false
              },
              {
                label:'Work added',
                showMarker: false,
                color: '#0066CC',
                shadow: false
              }
             ],
      legend: {
        renderer: $.jqplot.EnhancedLegendRenderer,
        show: true,
        placement: 'outside',
        location: 'n',
        fontSize: '12px',
        background: '#DFEEFD',
        border: 0,
        rendererOptions: {
          numberRows: 1
        }
      }
    });

    // Makes the data points clickable, redirecting the user to the timeline
    var timeline_url = data['timeline_url'];
    $('#chart1').bind('jqplotDataClick',
      function (ev, seriesIndex, pointIndex, data, neighbor, gridData) {
        // data[0] is a unix timestamp
        new_date = new Date(data[0]);
        year = new_date.getFullYear();
        // Necessary check as getDate and getMonth not always MM or DD format
        // Remember JS date months are zero based hence the +1
        if (new_date.getMonth() +1 <= 9) {
          month = "0" + (new_date.getMonth() +1);
        }
        else {
          month = new_date.getMonth() +1;
        }
        if (new_date.getDate() <= 9) {
          day = "0" + new_date.getDate();
        }
        else {
          day = new_date.getDate();
        }
        date_string = year + "-" + month + "-" + day;
        // redirect to the timeline page for that date
        window.location = (timeline_url + '&from=' + date_string);
      }
    );
  }

  function redraw_burndown(data, metric) {
    //Redraw the burn down chart with new data returned from JSON
    var burndowncurve = dataSeries(data['burndowndata']);
    var teameffortcurve = dataSeries(data['teameffortdata']);
    var idealcurve = dataSeries(data['idealcurvedata']);
    var addedcurve = dataSeries(data['workaddeddata']);

    var options = {
      axis: {
        yaxis: {
          legend: 'Effort ' + metric
        }
      },
      highlighter: {
        formatString: '%s - %s ' + metric
      }
    }
    plot1.replot({data:[idealcurve, burndowncurve, teameffortcurve, addedcurve]}, options);
  }

  function burndown_fail() {
    $("#chart1").html("<span class='block center'> Failed to retrieve burn \
                      down data.</span>")
                .attr("class", "box-info");
  }

  function show_spinner(chartname) {
    $(chartname).addClass("center")
                 .append("<i id='burndown-spinner' class='icon-spinner icon-spin icon-4x'></i>");
  }

  function remove_spinner(chartname) {
    $(chartname).removeClass("center");
    $("burndown-spinner").remove();
  }

  // Open a new window with the an image of the burndown chart
  $('#print-burndown').click(function() {
    //var $chart = $("#chart1");
    //var $burdown_image = $chart.jqplotToImageStr({});
    //var $burdown_image = $("#chart1").jqplotToImageStr({});
    window.open($("#chart1").jqplotToImageStr({}));
  });

});